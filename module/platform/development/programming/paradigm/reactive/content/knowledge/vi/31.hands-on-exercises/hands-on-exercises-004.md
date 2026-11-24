# Đọc dữ liệu theo lô và xử lý một bên tiêu thụ chậm

Trong một tác vụ đồng bộ dữ liệu, nguồn có thể đọc hàng nghìn bản ghi nhanh hơn dịch vụ đích có thể ghi. Nếu gửi từng bản ghi bằng một request riêng, chi phí network và round trip tăng cao. Nếu gom toàn bộ dữ liệu vào một danh sách, bộ nhớ có thể tăng đến mức không kiểm soát. Nếu gọi xử lý đồng thời không giới hạn, dịch vụ đích hoặc connection pool có thể bị quá tải.

Bài thực hành này xây dựng một pipeline Reactor đọc các đơn hàng đang chờ, gom chúng thành batch có kích thước và thời gian tối đa, rồi gửi lần lượt đến một consumer cố ý xử lý chậm. Bạn sẽ dùng `Flux`, `bufferTimeout`, `limitRate`, `concatMap` và `StepVerifier` để điều khiển nhịp đọc, giới hạn công việc đang chạy và kiểm tra hành vi khi downstream chậm.

## 1. Kịch bản và yêu cầu

Một hệ thống cần lưu trữ các đơn hàng cũ sang một dịch vụ archive. Repository có thể phát một `Flux<Order>` từ database. Dịch vụ archive nhận một danh sách đơn hàng trong mỗi request và mất khoảng 200 ms để xử lý một batch.

Thiết kế cần đáp ứng:

- Mỗi batch có tối đa 100 đơn hàng.
- Nếu chưa đủ 100 đơn, phát batch sau tối đa 500 ms để không giữ các bản ghi đầu tiên quá lâu.
- Chỉ xử lý một batch tại một thời điểm để giữ thứ tự và giới hạn tải lên archive service.
- Đọc theo demand của pipeline, tránh gom toàn bộ kết quả vào bộ nhớ.
- Nếu một lần ghi batch vượt quá 3 giây, phát timeout để xử lý lỗi.
- Chỉ đánh dấu batch đã hoàn tất sau khi archive service xác nhận thành công.

Luồng tổng quát:

~~~mermaid
flowchart LR
    A[Database Flux<Order>] --> B[limitRate]
    B --> C[bufferTimeout]
    C --> D[concatMap: một batch đang xử lý]
    D --> E[Archive service chậm]
    E --> F[Receipt]
~~~

`bufferTimeout` giải quyết việc gom dữ liệu; `concatMap` điều khiển số publisher con đang hoạt động; demand được truyền ngược từ consumer về nguồn. Ba cơ chế này bổ sung cho nhau.

## 2. Chuẩn bị kiểu dữ liệu và hợp đồng

Bắt đầu với các kiểu dữ liệu tối thiểu:

~~~java
import java.math.BigDecimal;
import java.time.Duration;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record Order(long id, String customerId, BigDecimal total) {}

record ArchiveReceipt(int accepted, long lastOrderId) {}

interface OrderRepository {
    Flux<Order> findPendingOrders();
}

interface ArchiveClient {
    Mono<ArchiveReceipt> archive(List<Order> orders);
}
~~~

Repository trả về `Flux<Order>` để database adapter có thể phát các hàng theo demand. Archive client trả về `Mono<ArchiveReceipt>` vì mỗi lần gửi một batch chỉ có một kết quả xác nhận hoặc một lỗi.

Trong ứng dụng thực tế, `findPendingOrders()` nên dùng một truy vấn có thứ tự ổn định, ví dụ theo khóa chính. Nếu dữ liệu lớn, cấu hình fetch size của driver hoặc dùng keyset pagination. `limitRate` ở Reactor điều tiết request giữa các publisher; nó không tự cấu hình kích thước fetch của database driver.

## 3. Tạo pipeline đọc và gom batch

Đầu tiên, viết một pipeline chỉ gom dữ liệu:

~~~java
Flux<List<Order>> batches = repository.findPendingOrders()
    .bufferTimeout(100, Duration.ofMillis(500));
~~~

`bufferTimeout(100, Duration.ofMillis(500))` phát batch khi một trong hai điều kiện xảy ra:

- Batch đã có 100 đơn hàng.
- Đã trôi qua 500 ms kể từ khi batch bắt đầu chờ dữ liệu.

Nếu nguồn complete khi batch cuối chưa đủ 100 phần tử, các phần tử còn lại vẫn được phát thành batch cuối. Vì vậy, consumer cần chấp nhận batch có kích thước nhỏ hơn giới hạn.

Để nhìn rõ dữ liệu đầu ra, có thể thử với nguồn hữu hạn:

~~~java
Flux<List<Integer>> batches = Flux.range(1, 7)
    .buffer(3);
~~~

Nguồn trên tạo ba batch: [1, 2, 3], [4, 5, 6] và [7]. `buffer(3)` chỉ gom theo kích thước; `bufferTimeout` còn có điều kiện thời gian để batch không phải chờ mãi khi nguồn phát chậm.

Không dùng `collectList()` cho toàn bộ nguồn lớn. `collectList()` chỉ phát một danh sách khi upstream complete và giữ toàn bộ phần tử trong bộ nhớ. `bufferTimeout` giữ dữ liệu theo từng nhóm nhỏ hơn, phù hợp với pipeline xử lý liên tục.

## 4. Điều tiết request từ nguồn

Thêm `limitRate` trước bước gom batch:

~~~java
Flux<List<Order>> batches = repository.findPendingOrders()
    .limitRate(128)
    .bufferTimeout(100, Duration.ofMillis(500));
~~~

`limitRate(128)` chia các request lớn từ downstream thành các đợt request upstream nhỏ hơn theo chính sách replenishment của Reactor. Nó không giới hạn tổng số đơn hàng được đọc. Nó cũng không thay thế fetch size hoặc pagination ở database.

Khi nguồn là một publisher tuân thủ Reactive Streams, request được truyền ngược để nguồn chỉ phát lượng dữ liệu mà pipeline có thể tiêu thụ. Nếu nguồn là callback API hoặc hot source không thể giảm tốc, cần một chính sách riêng cho dữ liệu đến khi downstream chưa có demand: buffer có giới hạn và overflow rõ ràng, drop nếu nghiệp vụ cho phép, hoặc ghi vào durable queue.

Không thêm `onBackpressureBuffer()` không giới hạn để che một consumer chậm. Buffer không giới hạn chỉ trì hoãn thời điểm quá tải xuất hiện và có thể làm heap tăng liên tục.

## 5. Xử lý một batch tại một thời điểm

Giả sử archive service mất 200 ms để ghi mỗi batch. `concatMap` chỉ chuyển sang batch tiếp theo khi publisher con của batch hiện tại hoàn tất:

~~~java
Flux<ArchiveReceipt> receipts = repository.findPendingOrders()
    .limitRate(128)
    .bufferTimeout(100, Duration.ofMillis(500))
    .concatMap(batch -> archiveClient.archive(batch), 1);
~~~

Tham số `1` đặt prefetch của `concatMap` ở mức nhỏ. `concatMap` giữ thứ tự batch và chỉ có một publisher con đang được xử lý tại một thời điểm. Khi archive service chậm, downstream chưa yêu cầu xử lý batch kế tiếp; demand được truyền ngược qua operator về nguồn.

Không thay `concatMap` bằng `flatMap` không giới hạn. `flatMap` có thể subscribe nhiều request archive cùng lúc và phát receipt theo thứ tự hoàn tất. Nếu các batch độc lập và dịch vụ đích chịu được concurrency, có thể dùng `flatMap` với giới hạn rõ ràng, chẳng hạn:

~~~java
Flux<ArchiveReceipt> receipts = batches.flatMap(
    batch -> archiveClient.archive(batch),
    4
);
~~~

Concurrency bằng 4 cho phép tối đa bốn publisher con hoạt động đồng thời theo hợp đồng của operator. Hãy đo connection pool, giới hạn rate và khả năng của dịch vụ đích trước khi tăng con số. Nếu cần giữ thứ tự receipt, `concatMap` là lựa chọn đơn giản hơn.

## 6. Hoàn thiện service có timeout và quan sát

Đóng gói các hằng số và pipeline vào service:

~~~java
import java.time.Duration;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

class OrderArchiveService {
    private static final int BATCH_SIZE = 100;
    private static final int SOURCE_RATE = 128;
    private static final Duration MAX_BATCH_WAIT =
        Duration.ofMillis(500);
    private static final Duration ARCHIVE_TIMEOUT =
        Duration.ofSeconds(3);

    private final OrderRepository repository;
    private final ArchiveClient archiveClient;

    OrderArchiveService(
            OrderRepository repository,
            ArchiveClient archiveClient) {
        this.repository = repository;
        this.archiveClient = archiveClient;
    }

    Flux<ArchiveReceipt> archivePendingOrders() {
        return repository.findPendingOrders()
            .limitRate(SOURCE_RATE)
            .bufferTimeout(BATCH_SIZE, MAX_BATCH_WAIT)
            .concatMap(this::archiveBatch, 1)
            .checkpoint("order-archive.batch-pipeline");
    }

    private Mono<ArchiveReceipt> archiveBatch(List<Order> batch) {
        return archiveClient.archive(List.copyOf(batch))
            .switchIfEmpty(Mono.error(
                new IllegalStateException("Archive completed without a receipt")
            ))
            .flatMap(receipt -> {
                if (receipt.accepted() != batch.size()) {
                    return Mono.error(new IllegalStateException(
                        "Archive accepted " + receipt.accepted()
                            + " of " + batch.size() + " orders"
                    ));
                }
                return Mono.just(receipt);
            })
            .timeout(ARCHIVE_TIMEOUT);
    }
}
~~~

`List.copyOf(batch)` chuyển batch thành danh sách không thể sửa trước khi giao cho client. Điều này giúp tránh một consumer vô tình thay đổi collection do pipeline tạo ra.

Service yêu cầu receipt và xác minh số bản ghi được chấp nhận bằng đúng kích thước batch trước khi phát receipt cho downstream. Một `Mono.empty()` hoặc receipt chỉ xác nhận một phần batch sẽ trở thành lỗi, nên caller không thể nhầm completion rỗng với xác nhận lưu trữ thành công.

`timeout` giới hạn thời gian chờ phản hồi archive. Khi timeout, downstream nhận `TimeoutException` và subscription của publisher con bị hủy. Điều đó không bảo đảm archive server đã dừng xử lý request; nếu request đã tới server, thao tác có thể vẫn được thực hiện. Vì vậy, endpoint archive nên hỗ trợ idempotency key, ví dụ khóa theo khoảng ID hoặc mã batch, để retry không tạo bản ghi trùng.

`checkpoint` thêm một dấu mốc có tên vào assembly traceback để hỗ trợ chẩn đoán khi pipeline lỗi. Chỉ đặt checkpoint ở ranh giới có ý nghĩa; không cần thêm vào mọi toán tử.

## 7. Vì sao pipeline không để consumer chậm làm cạn bộ nhớ?

Khi `archiveBatch` đang chạy, `concatMap` chưa chuyển sang publisher con kế tiếp. Nếu repository hỗ trợ backpressure, yêu cầu dữ liệu upstream được điều tiết theo lượng mà pipeline có thể xử lý. Các operator có thể giữ một lượng dữ liệu nội bộ để tạo batch hoặc chuẩn bị phần tử tiếp theo, nên cần kiểm soát cả batch size, prefetch và driver fetch size.

Hãy phân biệt các giới hạn:

| Cơ chế | Giới hạn điều gì? | Không bảo đảm điều gì? |
| --- | --- | --- |
| `bufferTimeout(100, 500 ms)` | Tối đa 100 phần tử trong một batch; flush theo thời gian | Không giới hạn mọi queue bên trong driver hoặc ứng dụng |
| `concatMap(..., 1)` | Xử lý publisher con tuần tự với prefetch nhỏ | Không điều khiển fetch size của database |
| `limitRate(128)` | Chia request upstream thành các đợt | Không giới hạn tổng số phần tử |
| Database fetch size | Số hàng driver lấy mỗi lượt, tùy driver | Không giới hạn queue ở archive client |
| Pagination | Kích thước một trang truy vấn | Không tự điều tiết tốc độ ghi của consumer |

Một pipeline có backpressure không đồng nghĩa mọi thành phần bên dưới đều có thể dừng hoặc điều tiết. Hãy kiểm tra từng adapter và cấu hình driver.

## 8. Thử nghiệm hành vi batch với StepVerifier

Kiểm tra rằng nguồn hữu hạn tạo các batch đúng kích thước và giữ phần dư:

~~~java
import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class BatchPipelineTest {
    @Test
    void emitsFullBatchesAndFinalPartialBatch() {
        Flux<List<Integer>> batches = Flux.range(1, 7)
            .bufferTimeout(3, Duration.ofSeconds(1));

        StepVerifier.create(batches)
            .expectNext(
                List.of(1, 2, 3),
                List.of(4, 5, 6),
                List.of(7)
            )
            .verifyComplete();
    }
}
~~~

Nguồn `range` phát đồng bộ và complete nhanh, nên batch cuối được flush khi nguồn hoàn tất. Test không cần chờ một giây.

Thêm một test để xác minh batch được flush theo thời gian ngay cả khi nguồn chưa complete:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.concat(
            Flux.just(1, 2),
            Mono.delay(Duration.ofMillis(600))
                .thenMany(Flux.just(3))
        )
        .bufferTimeout(10, Duration.ofMillis(500))
    )
    .thenAwait(Duration.ofMillis(500))
    .expectNext(List.of(1, 2))
    .thenAwait(Duration.ofMillis(100))
    .expectNext(List.of(3))
    .verifyComplete();
~~~

Hai phần tử đầu được phát thành batch sau 500 ms, trước khi phần tử thứ ba đến ở mốc 600 ms. Phần tử cuối được flush khi nguồn complete. Test dùng virtual time nên không phải chờ thời gian thực.

## 9. Mô phỏng consumer chậm và xác minh concurrency

Tạo một consumer mất 100 ms cho mỗi batch. Dùng `concatMap` để bảo đảm chỉ một batch đang được xử lý:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class SlowConsumerTest {
    @Test
    void processesOnlyOneBatchAtATime() {
        AtomicInteger inFlight = new AtomicInteger();
        AtomicInteger maxInFlight = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Flux.range(1, 6)
                    .buffer(2)
                    .concatMap(batch -> Mono.defer(() -> {
                        int active = inFlight.incrementAndGet();
                        maxInFlight.accumulateAndGet(active, Math::max);

                        return Mono.delay(Duration.ofMillis(100))
                            .thenReturn(batch.size())
                            .doFinally(signal ->
                                inFlight.decrementAndGet()
                            );
                    }), 1)
            )
            .thenAwait(Duration.ofMillis(300))
            .expectNext(2, 2, 2)
            .verifyComplete();

        assertEquals(1, maxInFlight.get());
        assertEquals(0, inFlight.get());
    }
}
~~~

`Mono.defer` tăng bộ đếm khi publisher con thực sự được subscribe. `doFinally` giảm bộ đếm ở mọi đường kết thúc của publisher con. Virtual time giúp ba batch hoàn tất mà không cần chờ 300 ms ngoài đời. Assertion `maxInFlight == 1` xác nhận không có hai batch cùng chạy.

Nếu đổi `concatMap` sang `flatMap` với concurrency lớn hơn một, test có thể quan sát nhiều batch cùng hoạt động. Khi đó, cần cập nhật kỳ vọng theo giới hạn concurrency mới thay vì giả định xử lý tuần tự.

## 10. Thử nghiệm timeout và lỗi archive

Một batch có thể thất bại vì timeout hoặc lỗi từ archive service. Hãy xác minh lỗi được truyền ra ngoài pipeline:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.<ArchiveReceipt>never()
            .timeout(Duration.ofSeconds(3))
    )
    .thenAwait(Duration.ofSeconds(3))
    .expectError(java.util.concurrent.TimeoutException.class)
    .verify();
~~~

Trong service thật, nếu một batch lỗi thì `concatMap` mặc định kết thúc pipeline bằng lỗi và không tiếp tục các batch sau. Đây thường là hành vi an toàn khi cần biết chính xác batch nào chưa được xác nhận. Nếu nghiệp vụ cho phép tiếp tục, hãy xử lý lỗi bên trong mapper với một chính sách rõ ràng, đồng thời ghi nhận batch thất bại để retry hoặc đối soát.

Không dùng `onErrorResume(error -> Mono.empty())` để âm thầm bỏ batch lỗi. Consumer có thể thấy pipeline hoàn tất bình thường dù dữ liệu chưa được archive.

## 11. Nguồn không hỗ trợ backpressure

Không phải nguồn nào cũng là publisher có thể điều tiết. Một callback API có thể đẩy event vào ứng dụng theo tốc độ riêng. Với loại nguồn này, `limitRate` ở downstream không làm callback producer chậm lại.

Trước khi nối một nguồn push vào pipeline, chọn chính sách rõ ràng:

- **Bounded buffer:** giữ tối đa N event và phát lỗi hoặc kích hoạt overflow handler khi đầy.
- **Drop:** bỏ event khi không có capacity, chỉ khi nghiệp vụ cho phép mất dữ liệu.
- **Latest:** giữ trạng thái mới nhất, phù hợp với telemetry trạng thái chứ không phải lịch sử giao dịch.
- **Durable queue/broker:** chuyển áp lực sang một hàng đợi có lưu trữ và chính sách retention.

Với event nghiệp vụ không được mất, không dùng drop/latest. Hãy đưa dữ liệu vào một hàng đợi bền vững hoặc yêu cầu producer hỗ trợ acknowledgement và flow control.

## 12. Bài tập mở rộng

Sau khi hoàn thành pipeline cơ bản, hãy thử các thay đổi sau:

1. Đổi batch size từ 100 xuống 20 và đo số request archive tăng bao nhiêu.
2. Đổi `MAX_BATCH_WAIT` từ 500 ms xuống 100 ms; quan sát số batch nhỏ khi nguồn phát chậm.
3. Thay `concatMap` bằng `flatMap` có concurrency bằng 2; xác minh số batch đang chạy đồng thời không vượt giới hạn.
4. Làm archive service chậm gấp đôi; quan sát thời gian hoàn tất và lượng dữ liệu chờ.
5. Làm archive service lỗi ở batch thứ hai; xác định batch nào đã được xác nhận và batch nào cần retry.
6. Thêm idempotency key cho mỗi batch và kiểm thử gửi lại cùng batch hai lần.
7. Thay nguồn repository bằng callback push không thể backpressure; chọn overflow policy có giới hạn.
8. Nếu dùng database lớn, thử keyset pagination và lưu checkpoint ID sau mỗi batch được xác nhận.

### Tiêu chí hoàn thành

- Batch không vượt quá kích thước cấu hình.
- Batch cuối hoặc batch hết thời gian vẫn được phát khi có phần tử.
- Số batch đang xử lý đồng thời không vượt giới hạn đã chọn.
- Pipeline không dùng `collectList()` để giữ toàn bộ nguồn.
- Timeout và lỗi archive được thể hiện rõ cho caller hoặc được ghi vào cơ chế retry có thể đối soát.
- Cancellation và lỗi không làm batch chưa xác nhận bị đánh dấu hoàn tất.
- Test dùng `StepVerifier`, không dùng `Thread.sleep` để đồng bộ thời gian.

## 13. Lỗi thường gặp khi đọc batch với consumer chậm

- **Gom tất cả vào `collectList()`:** giữ toàn bộ dữ liệu trong heap và chỉ phát khi nguồn complete.
- **Dùng buffer không giới hạn:** tốc độ producer cao hơn consumer làm queue tăng mãi.
- **Gửi mọi batch bằng `flatMap` không giới hạn:** tạo quá nhiều request đồng thời và có thể làm cạn pool.
- **Nhầm `limitRate` với fetch size:** request window của Reactor và fetch của database driver là hai tầng khác nhau.
- **Chỉ dùng `buffer(n)` cho nguồn phát thưa:** batch cuối có thể phải chờ nguồn complete mới được phát; dùng `bufferTimeout` nếu cần flush theo thời gian.
- **Cho rằng timeout chắc chắn dừng server:** timeout hủy subscription upstream nhưng server có thể đã nhận và thực hiện request.
- **Retry batch ghi mà không có idempotency:** có thể ghi trùng khi lần trước đã thành công nhưng response bị mất.
- **Nuốt lỗi để pipeline tiếp tục:** dữ liệu chưa archive có thể bị bỏ qua mà không có trạng thái phục hồi.
- **Giữ một transaction cho toàn bộ quá trình dài:** connection và lock có thể bị giữ lâu; ưu tiên transaction ngắn theo batch khi nghiệp vụ cho phép.

## 14. Tổng kết bài thực hành

Pipeline đọc theo lô cần cân bằng kích thước batch, thời gian chờ và tốc độ consumer. `bufferTimeout` tạo batch có giới hạn theo số phần tử hoặc thời gian; `limitRate` điều tiết request đến nguồn; `concatMap` xử lý tuần tự và giới hạn publisher con đang hoạt động; `StepVerifier` xác minh batch, concurrency, timeout và terminal signal. Khi consumer chậm, hãy để backpressure truyền về nguồn nếu adapter hỗ trợ; nếu nguồn chỉ push, phải đặt một giới hạn buffer hoặc dùng durable queue với chính sách overflow cụ thể. Với thao tác ghi có side effect, dùng idempotency và chỉ ghi nhận tiến độ sau khi nhận xác nhận thành công. Những lựa chọn đó giúp tác vụ xử lý dữ liệu lớn giữ được bộ nhớ, tải dịch vụ đích và trạng thái dữ liệu trong giới hạn dự đoán được.
