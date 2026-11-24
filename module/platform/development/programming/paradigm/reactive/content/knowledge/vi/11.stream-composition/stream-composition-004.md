# flatMapSequential: xử lý đồng thời nhưng phát theo thứ tự

Trong một pipeline reactive, mỗi phần tử đầu vào có thể cần gọi một Publisher khác để lấy thêm dữ liệu. Nếu các lời gọi hoàn tất với thời gian khác nhau, kết quả có thể đến không theo thứ tự ban đầu. Có lúc ta muốn tận dụng xử lý đồng thời để tăng throughput, đồng thời vẫn giữ thứ tự kết quả theo luồng đầu vào.

Project Reactor cung cấp `flatMapSequential` cho tình huống đó. Toán tử đăng ký các Publisher con đồng thời trong giới hạn cấu hình, nhưng giữ kết quả theo thứ tự các phần tử nguồn đã tạo ra chúng.

Ví dụ, hệ thống nhận các mã đơn hàng theo thứ tự `ORD-101`, `ORD-102`, `ORD-103`. Mỗi mã cần gọi dịch vụ lấy lịch sử xử lý. Dịch vụ có thể trả kết quả cho đơn hàng thứ ba trước đơn hàng thứ nhất. Nếu giao diện hoặc bước xuất báo cáo yêu cầu thứ tự đầu vào, `flatMapSequential` cho phép các yêu cầu chạy đồng thời mà vẫn phát các nhóm kết quả theo thứ tự đơn hàng.

## 1. Bài toán: hoàn tất không theo thứ tự đầu vào

Giả sử nguồn phát ba mã đơn hàng theo thứ tự:

~~~java
Flux<String> orderIds = Flux.just(
    "ORD-101",
    "ORD-102",
    "ORD-103"
);
~~~

Mỗi mã được chuyển thành một lời gọi bất đồng bộ:

~~~java
Flux<OrderSummary> summaries = orderIds
    .flatMap(id -> orderService.loadSummary(id));
~~~

`flatMap` đăng ký nhiều Publisher con và phát kết quả ngay khi chúng đến. Nếu lời gọi cho `ORD-103` hoàn tất trước `ORD-101`, kết quả của `ORD-103` có thể xuất hiện trước. Đây là hành vi đúng của `flatMap`; toán tử ưu tiên hợp nhất kết quả, không bảo đảm thứ tự theo nguồn.

Trong một số luồng, thứ tự hoàn tất không quan trọng. Nhưng với các trường hợp như dựng báo cáo theo thứ tự sự kiện, phát các nhóm dữ liệu theo thứ tự yêu cầu hoặc ghép kết quả theo thứ tự đầu vào, việc kết quả đến lộn xộn có thể làm tầng sau phức tạp hơn.

`flatMapSequential` giải quyết yêu cầu này bằng cách cho phép nhiều Publisher con hoạt động cùng lúc, sau đó sắp xếp việc phát kết quả theo thứ tự các phần tử nguồn đã tạo ra từng Publisher con.

## 2. Cách flatMapSequential hoạt động

Cấu trúc tổng quát:

~~~java
Flux<R> result = source.flatMapSequential(
    value -> createInnerPublisher(value),
    maxConcurrency,
    prefetch
);
~~~

Toán tử thực hiện ba việc:

1. Nhận phần tử từ Publisher nguồn theo thứ tự.
2. Áp dụng mapper và đăng ký các Publisher con, tối đa `maxConcurrency` nhánh đang hoạt động.
3. Giữ kết quả từ các nhánh phía sau nếu cần, rồi phát theo thứ tự nhánh tương ứng với phần tử nguồn.

Giả sử nguồn phát A, B, C. Các Publisher con có thể hoàn tất theo thứ tự C, B, A. `flatMapSequential` vẫn phát các phần tử thuộc nhóm A trước, sau đó đến nhóm B và nhóm C.

~~~mermaid
sequenceDiagram
    participant O as Outer Publisher
    participant A as Inner A
    participant B as Inner B
    participant C as Inner C
    participant D as Downstream

    O->>A: subscribe(A)
    O->>B: subscribe(B)
    O->>C: subscribe(C)
    B-->>B: hoàn tất sớm
    C-->>C: hoàn tất tiếp
    A-->>A: hoàn tất sau
    A-->>D: phát kết quả nhóm A
    B-->>D: phát kết quả nhóm B đã đệm
    C-->>D: phát kết quả nhóm C đã đệm
~~~

Sơ đồ cho thấy thứ tự phát kết quả có thể khác thứ tự hoàn tất của các Publisher con. Nhánh B và C có thể hoàn tất trước nhưng kết quả được giữ lại cho đến khi nhóm A được phát xong.

Điều này có nghĩa `flatMapSequential` không sắp xếp kết quả theo giá trị hoặc theo một khóa nghiệp vụ. Nó giữ thứ tự nhóm theo thứ tự phần tử của Publisher nguồn. Nếu nguồn phát B rồi A, nhóm B vẫn được phát trước nhóm A, bất kể thứ tự chữ cái hoặc thời điểm hoàn tất.

## 3. Ví dụ lấy dữ liệu chi tiết cho nhiều đơn hàng

Giả sử mỗi đơn hàng có thể có nhiều sự kiện lịch sử. Dịch vụ `auditClient.eventsFor(orderId)` trả về `Flux<AuditEntry>`. Ta muốn tải lịch sử cho nhiều đơn hàng cùng lúc, nhưng giữ toàn bộ sự kiện của đơn hàng trước trước khi phát sự kiện của đơn hàng tiếp theo.

~~~java
import reactor.core.publisher.Flux;

Flux<AuditEntry> orderedAudit = orderIds
    .flatMapSequential(
        auditClient::eventsFor,
        8,
        16
    );
~~~

Trong ví dụ:

- `auditClient::eventsFor` tạo một Publisher con cho mỗi mã đơn hàng.
- `8` là giới hạn số Publisher con được đăng ký đồng thời.
- `16` là prefetch cho mỗi Publisher con.
- Kết quả vẫn là `Flux<AuditEntry>`.

Giả sử nguồn phát `ORD-101`, `ORD-102`, `ORD-103`. Dịch vụ có thể tải xong lịch sử của `ORD-103` trước, nhưng các sự kiện của đơn hàng này được giữ lại cho đến khi các nhóm đứng trước đã được phát. Downstream nhận các nhóm theo thứ tự `ORD-101`, `ORD-102`, `ORD-103`.

Nếu mỗi phần tử nguồn chỉ tạo một kết quả duy nhất, chẳng hạn gọi một dịch vụ trả về `Mono<OrderSummary>`, toán tử vẫn có ích:

~~~java
Flux<OrderSummary> orderedSummaries = orderIds
    .flatMapSequential(
        orderService::loadSummary,
        8,
        1
    );
~~~

Với Publisher con kiểu Mono, mỗi nhánh có tối đa một phần tử dữ liệu. `maxConcurrency` vẫn quyết định số lời gọi có thể hoạt động đồng thời; prefetch 1 phù hợp với một kết quả cho mỗi nhánh.

Các kiểu `OrderId`, `AuditEntry`, `OrderSummary` và dịch vụ trong ví dụ là kiểu miền do ứng dụng định nghĩa.

## 4. So sánh flatMapSequential, flatMap và concatMap

Ba toán tử đều nhận một mapper tạo Publisher con, nhưng có cách điều phối và phát kết quả khác nhau:

| Toán tử | Đăng ký Publisher con | Thứ tự phát kết quả | Đặc điểm |
|---|---|---|---|
| `flatMap` | Có thể đăng ký nhiều nhánh đồng thời | Theo thời điểm kết quả đến | Ưu tiên throughput và không giữ thứ tự nguồn. |
| `flatMapSequential` | Đăng ký nhiều nhánh đồng thời trong giới hạn | Theo thứ tự phần tử nguồn | Có thể đệm kết quả của nhánh hoàn tất sớm. |
| `concatMap` | Xử lý Publisher con lần lượt | Theo thứ tự phần tử nguồn | Chỉ chuyển sang nhánh kế tiếp sau khi nhánh trước hoàn tất. |

Ví dụ cùng một mapper:

~~~java
Flux<Result> unordered = ids.flatMap(this::load);
Flux<Result> orderedConcurrent = ids.flatMapSequential(this::load);
Flux<Result> orderedSequential = ids.concatMap(this::load);
~~~

Chọn toán tử theo yêu cầu:

- Dùng `flatMap` khi thứ tự không quan trọng và muốn hợp nhất kết quả ngay khi có.
- Dùng `flatMapSequential` khi muốn xử lý nhiều nhánh đồng thời nhưng downstream cần thứ tự nguồn.
- Dùng `concatMap` khi phải xử lý tuần tự, chẳng hạn thao tác sau phụ thuộc trạng thái do thao tác trước tạo ra hoặc không muốn có nhiều lời gọi đang hoạt động cùng lúc.

Giữ thứ tự không đồng nghĩa với chạy tuần tự. `flatMapSequential` cho phép các nhánh phía sau bắt đầu và hoàn tất trong khi nhánh trước vẫn đang chạy. Chính khả năng này giúp tăng mức độ sử dụng tài nguyên so với `concatMap` trong những tác vụ độc lập.

## 5. Quan sát thứ tự phát bằng ví dụ thời gian

Ta có thể mô phỏng ba lời gọi có độ trễ khác nhau. Nhánh A mất 300 ms, B mất 100 ms và C mất 50 ms. Các Publisher con có thể hoàn tất theo thứ tự C, B, A, nhưng đầu ra vẫn là A, B, C.

~~~java
import java.time.Duration;
import java.util.function.Function;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Function<String, Duration> delayFor = id -> switch (id) {
    case "A" -> Duration.ofMillis(300);
    case "B" -> Duration.ofMillis(100);
    default -> Duration.ofMillis(50);
};

Flux<String> ordered = Flux.just("A", "B", "C")
    .flatMapSequential(
        id -> Mono.delay(delayFor.apply(id)).thenReturn(id),
        3,
        1
    );
~~~

`Mono.delay` tạo một Publisher chỉ phát sau khoảng thời gian đã định. Vì `maxConcurrency` là 3, cả ba nhánh có thể được đăng ký mà không cần đợi nhánh trước hoàn tất. Dù C và B hoàn tất trước, kết quả được phát theo thứ tự A, B, C.

Có thể kiểm tra bằng StepVerifier và virtual time:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void flatMapSequentialGiuThuTuNguon() {
    StepVerifier.withVirtualTime(() ->
            Flux.just("A", "B", "C")
                .flatMapSequential(
                    id -> Mono.delay(
                            Duration.ofMillis(id.equals("A") ? 300 : 50)
                        ).thenReturn(id),
                    3,
                    1
                )
        )
        .thenAwait(Duration.ofMillis(300))
        .expectNext("A", "B", "C")
        .verifyComplete();
}
~~~

Supplier truyền vào `withVirtualTime` giúp pipeline được tạo sau khi virtual scheduler được cài đặt. Phép thử xác nhận thứ tự phát cuối cùng; để xác minh mức đồng thời thực tế trong một hệ thống, cần kiểm tra thêm số nhánh đang hoạt động hoặc dùng công cụ quan sát phù hợp.

## 6. maxConcurrency: giới hạn số nhánh đang hoạt động

`maxConcurrency` xác định số Publisher con tối đa được đăng ký đồng thời. Đây là giới hạn quan trọng khi mapper gọi dịch vụ bên ngoài, truy vấn cơ sở dữ liệu hoặc thực hiện công việc có chi phí.

~~~java
Flux<EnrichedOrder> enriched = orders
    .flatMapSequential(
        order -> enrichmentService.enrich(order),
        6,
        8
    );
~~~

Với `maxConcurrency = 6`, tối đa sáu Publisher con có thể được hoạt động cùng lúc. Khi một nhánh hoàn tất và một vị trí được giải phóng, toán tử có thể lấy thêm phần tử nguồn và đăng ký nhánh kế tiếp.

Nếu concurrency quá thấp, pipeline có thể không tận dụng hết năng lực dịch vụ đích. Nếu quá cao, ứng dụng có thể tạo quá nhiều request đồng thời, tăng áp lực lên connection pool, thread, bộ nhớ và dịch vụ phụ thuộc.

Hãy chọn concurrency theo giới hạn thực tế:

- Khả năng chịu tải của dịch vụ được gọi.
- Kích thước connection pool và giới hạn request đồng thời.
- Chi phí CPU hoặc I/O của từng nhánh.
- Kích thước dữ liệu được giữ trong hàng đợi.
- Độ trễ p95/p99 và tỷ lệ lỗi khi tải tăng.

Concurrency chỉ giới hạn số Publisher con đang hoạt động. Nó không tự giới hạn tốc độ theo giây và cũng không bảo đảm tất cả nhánh sử dụng thread riêng. Cách thực thi phụ thuộc vào Publisher con và scheduler mà chúng sử dụng.

## 7. prefetch và bộ đệm giữ thứ tự

Tham số `prefetch` xác định số phần tử được yêu cầu trước từ mỗi Publisher con. Với một nhánh phát nhiều phần tử, toán tử có thể yêu cầu trước một lượng dữ liệu rồi giữ trong hàng đợi trong khi downstream tiêu thụ.

~~~java
Flux<AuditEntry> orderedAudit = orderIds
    .flatMapSequential(
        auditClient::eventsFor,
        8,
        32
    );
~~~

Trong ví dụ, tối đa tám Publisher con hoạt động đồng thời và mỗi nhánh có prefetch 32. Nếu nhánh đầu tiên chậm, các nhánh phía sau có thể phát dữ liệu vào hàng đợi nhưng chưa được phát ra downstream. Đây là chi phí cần trả để giữ thứ tự.

Một ước lượng ban đầu cho lượng dữ liệu được yêu cầu từ các nhánh đang hoạt động là `maxConcurrency × prefetch`. Đây không phải giới hạn chính xác cho toàn bộ bộ nhớ của pipeline, vì còn có hàng đợi upstream, các toán tử khác, payload đang xử lý và cấu trúc dữ liệu nội bộ.

| Cấu hình | Tác động thường gặp |
|---|---|
| Concurrency thấp, prefetch thấp | Ít request đồng thời và ít dữ liệu đệm; throughput có thể thấp khi I/O chậm. |
| Concurrency cao, prefetch thấp | Nhiều nhánh cùng chạy nhưng mỗi nhánh yêu cầu ít phần tử trước. |
| Concurrency thấp, prefetch cao | Ít nhánh hoạt động nhưng mỗi nhánh có thể giữ nhiều phần tử hơn. |
| Concurrency cao, prefetch cao | Có thể tăng throughput, đồng thời tăng nguy cơ tích lũy dữ liệu và áp lực bộ nhớ. |

Không nên tăng cả hai tham số cùng lúc khi tối ưu. Hãy đo độ trễ, throughput, số phần tử đang chờ và bộ nhớ trước khi thay đổi cấu hình.

## 8. Head-of-line blocking: khi nhánh đầu tiên chậm

Giữ thứ tự tạo ra một hệ quả quan trọng: một nhánh đầu tiên chậm có thể làm chậm việc phát kết quả của các nhánh sau, dù các nhánh sau đã hoàn tất.

Hiện tượng này thường được gọi là head-of-line blocking. Ví dụ:

- Nhánh A mất 2 giây.
- Nhánh B mất 100 ms.
- Nhánh C mất 80 ms.

B và C hoàn tất sớm nhưng kết quả của chúng phải chờ A. Nếu B và C phát nhiều phần tử, dữ liệu có thể tích lũy trong các hàng đợi nội bộ.

~~~mermaid
flowchart TD
    A["Inner A: chậm, đang chạy"] --> W["Vùng chờ giữ thứ tự"]
    B["Inner B: đã hoàn tất"] --> W
    C["Inner C: đã hoàn tất"] --> W
    W --> O["Downstream: chờ A, sau đó B rồi C"]
~~~

Đây không phải lỗi của toán tử. Nó là hệ quả trực tiếp của yêu cầu giữ thứ tự. Nếu downstream không thực sự cần thứ tự nguồn, `flatMap` có thể phù hợp hơn và cho phép phát B, C ngay khi chúng sẵn sàng.

Một số cách giảm ảnh hưởng:

- Giảm thời gian xử lý của nhánh đầu tiên bằng tối ưu truy vấn hoặc cache.
- Giới hạn concurrency và prefetch để kiểm soát lượng dữ liệu có thể tích lũy.
- Chia nguồn thành các partition độc lập nếu nghiệp vụ chỉ yêu cầu thứ tự trong từng partition.
- Chọn `flatMap` nếu thứ tự không phải ràng buộc nghiệp vụ.
- Dùng `concatMap` nếu cần tuần tự tuyệt đối và không muốn nhiều nhánh cùng hoạt động.

Không nên thêm bước sort ở cuối để thay thế một cách máy móc. Sort thường cần giữ nhiều kết quả cho đến khi biết toàn bộ dữ liệu hoặc có ranh giới sắp xếp rõ ràng; `flatMapSequential` giữ thứ tự theo luồng nguồn ngay trong quá trình phát.

## 9. Xử lý lỗi trong các Publisher con

Mặc định, khi một Publisher con phát lỗi, lỗi được truyền xuống downstream và các nhánh còn lại có thể bị hủy theo chính sách lỗi tức thời của toán tử. Điều này phù hợp khi một lỗi làm cho toàn bộ kết quả không còn đáng tin cậy.

~~~java
Flux<OrderSummary> summaries = orderIds
    .flatMapSequential(
        id -> orderService.loadSummary(id),
        8,
        1
    )
    .onErrorMap(error ->
        new OrderSummaryException("Không thể tải dữ liệu đơn hàng", error)
    );
~~~

Nếu nghiệp vụ cho phép tiếp tục với các đơn hàng khác, có thể xử lý lỗi bên trong Publisher con:

~~~java
Flux<OrderResult> results = orderIds
    .flatMapSequential(
        id -> orderService.loadSummary(id)
            .map(summary -> OrderResult.success(id, summary))
            .onErrorResume(error ->
                Mono.just(OrderResult.failure(id, error))
            ),
        8,
        1
    );
~~~

Trong trường hợp này, lỗi của một đơn hàng được chuyển thành một kết quả lỗi có kiểu miền. Nhánh đó kết thúc bình thường sau khi phát kết quả thay thế, vì thế các nhóm tiếp theo vẫn có thể được phát theo thứ tự nguồn.

Nếu cần trì hoãn việc truyền lỗi cho đến khi các nhánh đang hoạt động được xử lý, Reactor cung cấp biến thể `flatMapSequentialDelayError`. Chỉ dùng khi chính sách nghiệp vụ muốn thu thập hoặc trì hoãn lỗi; cần cân nhắc rằng việc giữ dữ liệu và tiếp tục chạy các nhánh có thể tăng tài nguyên tiêu thụ.

## 10. Cancellation và vòng đời Publisher con

Khi downstream hủy subscription, `flatMapSequential` truyền yêu cầu cancellation đến nguồn và các Publisher con đang được quản lý. Điều này giúp dừng những công việc không còn cần thiết, với điều kiện nguồn và driver hỗ trợ cancellation.

Ví dụ, downstream chỉ cần ba kết quả:

~~~java
Flux<OrderSummary> firstThree = orderIds
    .flatMapSequential(
        orderService::loadSummary,
        8,
        1
    )
    .take(3);
~~~

Khi `take(3)` đã nhận đủ ba phần tử, nó hủy subscription upstream và hoàn tất downstream. Các nhánh đang hoạt động nhận cancellation. Công việc bên dưới có thể cần thời gian để dừng nếu request đã được gửi đến dịch vụ ngoài.

Cancellation không phải tín hiệu `onComplete` của từng Publisher con. Downstream có thể hoàn tất bình thường do `take`, trong khi các nhánh upstream bị hủy vì không còn cần kết quả.

## 11. Kiểm thử thứ tự và giới hạn đồng thời

`StepVerifier` giúp xác minh thứ tự phát của các phần tử. Với nguồn bất đồng bộ, có thể dùng virtual time để tạo các thời điểm hoàn tất khác nhau mà không phải chờ thời gian thực.

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void ketQuaDuocPhatTheoThuTuNguon() {
    StepVerifier.withVirtualTime(() ->
            Flux.just(1, 2, 3)
                .flatMapSequential(
                    value -> Mono.delay(
                            Duration.ofMillis(value == 1 ? 300 : 50)
                        )
                        .thenReturn(value),
                    3,
                    1
                )
        )
        .thenAwait(Duration.ofMillis(300))
        .expectNext(1, 2, 3)
        .verifyComplete();
}
~~~

Có thể kiểm thử concurrency bằng bộ đếm số nhánh đang hoạt động. Ví dụ dưới đây tăng bộ đếm khi mỗi nhánh bắt đầu và giảm khi nhánh kết thúc:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertEquals;

@Test
void soPublisherConDongThoiKhongVuotQuaGioiHan() {
    AtomicInteger active = new AtomicInteger();
    AtomicInteger maxObserved = new AtomicInteger();

    StepVerifier.withVirtualTime(() ->
            Flux.range(1, 20)
                .flatMapSequential(
                    value -> Mono.defer(() -> {
                        int current = active.incrementAndGet();
                        maxObserved.accumulateAndGet(current, Math::max);
                        return Mono.delay(Duration.ofMillis(10))
                            .thenReturn(value)
                            .doFinally(signal -> active.decrementAndGet());
                    }),
                    4,
                    1
                )
        )
        .thenAwait(Duration.ofMillis(100))
        .expectNextCount(20)
        .verifyComplete();

    assertEquals(4, maxObserved.get());
}
~~~

Trong ví dụ, `Mono.defer` tăng bộ đếm khi Publisher con được subscribe và `doFinally` giảm bộ đếm khi nhánh kết thúc. Cách đo này theo dõi số nhánh đang hoạt động thay vì chỉ đếm thời điểm kết quả được phát.

Các trường hợp nên kiểm thử thêm:

- Nhánh sau hoàn tất trước nhưng kết quả vẫn được phát sau nhánh trước.
- Một Publisher con phát nhiều phần tử; thứ tự trong từng nhóm và thứ tự giữa các nhóm được giữ.
- Nhánh đầu tiên chậm khiến kết quả nhánh sau được đệm.
- Lỗi trong một nhánh được truyền ngay hoặc chuyển thành kết quả lỗi theo chính sách.
- Cancellation từ downstream truyền đến các nhánh đang hoạt động.
- Thay đổi `maxConcurrency` và `prefetch` không làm thay đổi thứ tự đầu ra.

## 12. Khi nào nên dùng flatMapSequential?

`flatMapSequential` phù hợp khi mỗi phần tử nguồn tạo ra một Publisher độc lập, có thể chạy đồng thời, nhưng downstream cần kết quả theo thứ tự nguồn.

| Yêu cầu | Lựa chọn |
|---|---|
| Ưu tiên kết quả đến sớm, không cần giữ thứ tự | `flatMap` |
| Cần thứ tự nguồn và muốn nhiều nhánh chạy đồng thời | `flatMapSequential` |
| Cần thứ tự nguồn và chỉ xử lý một nhánh tại một thời điểm | `concatMap` |
| Cần sắp xếp theo khóa nghiệp vụ khác thứ tự nguồn | Tạo bước sắp xếp riêng với chiến lược lưu trữ phù hợp |

Trước khi chọn, hãy tự hỏi:

- Các Publisher con có độc lập để chạy đồng thời không?
- Downstream có thật sự cần thứ tự của Publisher nguồn không?
- Một nhánh chậm có thể làm các nhánh sau phải chờ quá lâu không?
- Giới hạn concurrency và prefetch có phù hợp với tài nguyên dịch vụ đích không?
- Khi một nhánh lỗi, toàn bộ luồng nên dừng hay tiếp tục với kết quả lỗi riêng?

`flatMapSequential` là lựa chọn cân bằng giữa xử lý đồng thời và thứ tự phát. Nó giúp tăng khả năng sử dụng tài nguyên khi các lời gọi độc lập, đồng thời giữ cấu trúc kết quả dễ dự đoán cho downstream. Đổi lại, pipeline có thể phải đệm kết quả và chịu head-of-line blocking khi nhánh đầu tiên chậm. Hiểu rõ concurrency, prefetch, lỗi và cancellation sẽ giúp sử dụng toán tử này đúng với yêu cầu của ứng dụng Java reactive.

