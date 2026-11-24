# Yêu cầu theo lô, nạp trước và điều chỉnh kích thước lô

Backpressure cho phép Subscriber thông báo lượng dữ liệu mình sẵn sàng nhận thông qua `request(n)`. Trong ứng dụng thực tế, yêu cầu từng phần tử một có thể tạo nhiều lần phối hợp; yêu cầu một lượng vừa đủ theo từng đợt thường giúp giảm chi phí giao tiếp và giữ cho luồng xử lý ổn định.

Project Reactor cung cấp các cơ chế liên quan nhưng giải quyết những việc khác nhau:

- **Yêu cầu theo lô (batched demand):** Subscriber gọi `request(n)` để yêu cầu thêm một nhóm gồm tối đa `n` phần tử.
- **Nạp trước (prefetch):** một toán tử yêu cầu trước một lượng phần tử từ upstream và giữ chúng trong hàng đợi nội bộ để downstream có thể tiêu thụ dần.
- **Gom phần tử thành lô (buffering):** toán tử gom nhiều phần tử thành một collection hoặc nhóm trước khi chuyển tiếp.
- **Điều chỉnh kích thước lô:** chọn lượng demand, prefetch hoặc số phần tử trong một batch dựa trên năng lực xử lý, độ trễ và giới hạn tài nguyên.

Các khái niệm này có liên hệ với nhau nhưng không đồng nghĩa. Hiểu ranh giới giữa chúng giúp tránh tạo hàng đợi quá lớn, tăng độ trễ hoặc gây áp lực bộ nhớ khi xử lý luồng dữ liệu.

## 1. Vì sao yêu cầu theo lô có ích?

Giả sử một Subscriber đọc sự kiện từ nguồn dữ liệu và xử lý từng sự kiện. Nếu nó gọi `request(1)` sau mỗi phần tử, Publisher nhận nhiều lần yêu cầu nhỏ. Với một pipeline có nhiều tầng bất đồng bộ, các lần phối hợp này có thể làm tăng overhead.

Thay vào đó, Subscriber có thể yêu cầu 32 phần tử một lần, xử lý nhóm đó rồi mới yêu cầu nhóm tiếp theo. Demand vẫn được tính theo số phần tử, nhưng các lần yêu cầu được gom thành đợt.

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Publisher

    S->>P: request(3)
    P-->>S: onNext(A)
    P-->>S: onNext(B)
    P-->>S: onNext(C)
    S->>P: request(3)
    P-->>S: onNext(D)
    P-->>S: onNext(E)
    P-->>S: onNext(F)
~~~

Trong sơ đồ, Subscriber yêu cầu ba phần tử mỗi lần. Nếu nguồn kết thúc sớm, Publisher có thể phát ít hơn số phần tử đã yêu cầu. Nếu nguồn tạm thời chưa có dữ liệu, Subscriber có thể phải chờ phần tử tiếp theo. Demand chưa sử dụng hết được giữ lại; nhiều lần gọi `request(n)` được cộng dồn vào nhu cầu chưa đáp ứng.

Yêu cầu theo lô hữu ích khi:

- Chi phí điều phối cho mỗi lần yêu cầu đáng kể.
- Subscriber xử lý dữ liệu theo nhóm tự nhiên.
- Nguồn có thể cung cấp dữ liệu nhanh hơn tốc độ xử lý, nhưng Subscriber vẫn muốn giới hạn lượng dữ liệu được phép phát.
- Cần cân bằng giữa throughput, độ trễ và lượng dữ liệu đang chờ.

Batch demand không có nghĩa Publisher phải gom các phần tử thành một danh sách. Mỗi lần `onNext(value)` vẫn mang một phần tử riêng. Muốn gom payload thành danh sách, cần dùng các toán tử như `buffer` hoặc `bufferTimeout`.

## 2. Chủ động yêu cầu theo lô bằng BaseSubscriber

Các overload `subscribe(...)` tiện lợi của Reactor thường yêu cầu demand không giới hạn thực tế. Khi cần điều khiển lượng phần tử được yêu cầu, có thể triển khai `BaseSubscriber` và gọi `request(n)` theo từng đợt.

Ví dụ sau yêu cầu 32 phần tử ban đầu. Sau khi xử lý hết 32 phần tử của đợt hiện tại, Subscriber mới yêu cầu đợt tiếp theo:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

final class BatchedSubscriber extends BaseSubscriber<OrderEvent> {
    private final int batchSize;
    private int remainingInBatch;

    BatchedSubscriber(int batchSize) {
        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize phải lớn hơn 0");
        }
        this.batchSize = batchSize;
    }

    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        requestNextBatch();
    }

    @Override
    protected void hookOnNext(OrderEvent event) {
        process(event);

        remainingInBatch--;
        if (remainingInBatch == 0) {
            requestNextBatch();
        }
    }

    private void requestNextBatch() {
        remainingInBatch = batchSize;
        request(batchSize);
    }

    private void process(OrderEvent event) {
        // Xử lý một sự kiện.
    }
}

Flux<OrderEvent> events = eventSource.events();
events.subscribe(new BatchedSubscriber(32));
~~~

`remainingInBatch` đếm số phần tử còn lại trong đợt demand hiện tại. Subscriber chỉ gọi request tiếp khi đã xử lý hết nhóm được yêu cầu. Vì callback `hookOnNext` được tuần tự hóa theo hợp đồng Reactive Streams, bộ đếm đơn giản này phù hợp với ví dụ.

Cần chú ý hai điểm:

- Batch demand giới hạn số phần tử được yêu cầu, không đảm bảo nguồn luôn có đủ số phần tử đó.
- Nếu `process(event)` khởi chạy công việc bất đồng bộ rồi trả về ngay, ví dụ này chỉ giới hạn số callback đã nhận, không giới hạn số tác vụ bất đồng bộ còn đang chạy. Khi xử lý bất đồng bộ, cần gắn việc yêu cầu batch tiếp theo với lúc nhóm tác vụ thực sự hoàn tất.

Không nên gọi `request(batchSize)` sau mọi `onNext` nếu ý định là yêu cầu theo lô. Làm vậy sẽ cộng thêm demand ở mỗi phần tử và có thể khiến tổng lượng demand tăng không giới hạn.

## 3. limitRate: chia demand thành các đợt upstream

Trong pipeline Reactor, thường không cần tự viết Subscriber để chia nhỏ demand. Toán tử `limitRate` giúp điều tiết lượng request mà downstream chuyển ngược lên upstream.

~~~java
import reactor.core.publisher.Flux;

Flux<OrderEvent> controlled = eventSource.events()
    .limitRate(64);
~~~

`limitRate(64)` chia các yêu cầu lớn từ downstream thành các đợt request upstream có kích thước được giới hạn bởi high tide là 64. Khi số phần tử đã tiêu thụ chạm ngưỡng bổ sung demand, Reactor yêu cầu thêm phần tử từ upstream.

Với overload chỉ nhận high tide, Reactor dùng ngưỡng low tide mặc định bằng khoảng 75% high tide để bổ sung demand trước khi đợt hiện tại cạn.

Có thể chỉ định cả high tide và low tide:

~~~java
import reactor.core.publisher.Flux;

Flux<OrderEvent> controlled = eventSource.events()
    .limitRate(64, 16);
~~~

| Tham số | Vai trò |
|---|---|
| `highTide` | Giới hạn lượng request upstream trong một đợt. |
| `lowTide` | Ngưỡng đã tiêu thụ để Reactor yêu cầu thêm phần tử. |

Với `limitRate(64, 16)`, toán tử có thể yêu cầu tối đa 64 phần tử trong một đợt và bổ sung demand khi lượng tiêu thụ đạt ngưỡng low tide. Việc chọn low tide nhỏ hơn high tide tạo khoảng thời gian để nạp thêm dữ liệu trước khi hàng đợi cạn.

Nếu dùng `limitRate(64, 0)`, cơ chế bổ sung demand theo ngưỡng thấp bị tắt; đợt request tiếp theo chỉ được gửi khi phần demand của đợt hiện tại đã được tiêu thụ hết. Đây là cách chia lô nghiêm ngặt hơn, có thể làm tăng nguy cơ downstream phải chờ khi nguồn có độ trễ.

`limitRate` điều tiết demand. Nó không gom các phần tử thành collection và không phải bộ giới hạn tốc độ theo giây. Nếu cần giới hạn số request trong một đơn vị thời gian, đó là bài toán rate limiting riêng.

## 4. Prefetch: nạp trước dữ liệu cho toán tử downstream

Prefetch là số phần tử mà một toán tử yêu cầu trước từ upstream để giữ sẵn trong hàng đợi nội bộ. Mục tiêu là để downstream có dữ liệu tiếp tục xử lý trong khi upstream đang tạo thêm dữ liệu.

Ví dụ, `publishOn` chuyển việc xử lý các toán tử phía sau sang một scheduler khác và sử dụng hàng đợi để nối hai phía:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

Flux<OrderEvent> processed = eventSource.events()
    .publishOn(Schedulers.parallel(), 32)
    .map(this::calculate);
~~~

Tham số `32` là prefetch của `publishOn`. Toán tử có thể yêu cầu trước một nhóm phần tử từ upstream, xếp chúng vào hàng đợi rồi phát cho downstream theo demand. Khi hàng đợi được tiêu thụ đến ngưỡng bổ sung, nó yêu cầu thêm dữ liệu.

Prefetch giúp giảm khoảng trống giữa các bước xử lý, đặc biệt khi upstream và downstream chạy trên các scheduler khác nhau. Nhưng prefetch quá lớn có thể:

- Tăng bộ nhớ dùng cho các hàng đợi nội bộ.
- Giữ dữ liệu lâu hơn trước khi xử lý, làm tăng độ trễ.
- Làm nhiều phần tử đã được yêu cầu vẫn tiếp tục đi qua các tầng trung gian sau khi nhu cầu downstream giảm.
- Che khuất một downstream chậm bằng cách tích lũy thêm dữ liệu chờ.

Prefetch quá nhỏ cũng có thể làm downstream thường xuyên phải chờ upstream nạp thêm dữ liệu, khiến throughput giảm khi nguồn có độ trễ.

Vì vậy, prefetch là tham số cân bằng giữa khả năng giữ pipeline bận và lượng dữ liệu đang chờ trong bộ nhớ.

## 5. Prefetch trong flatMap và các toán tử kết hợp

`flatMap` có thể chạy nhiều Publisher con đồng thời. Hai tham số thường được quan tâm là concurrency và prefetch:

~~~java
import reactor.core.publisher.Flux;

Flux<Receipt> receipts = orderIds
    .flatMap(
        id -> paymentClient.charge(id),
        8,
        16
    );
~~~

Trong ví dụ:

- `concurrency = 8` giới hạn tối đa số Publisher con được đăng ký đồng thời.
- `prefetch = 16` điều khiển lượng phần tử được yêu cầu trước từ mỗi Publisher con.

Nếu Publisher con chỉ phát một kết quả như `Mono<Receipt>`, mỗi nhánh thường chỉ có một phần tử. Với Publisher con phát nhiều phần tử, prefetch ảnh hưởng đến lượng dữ liệu được yêu cầu trước từ từng nhánh.

Concurrency và prefetch có thể cùng làm tăng lượng dữ liệu đang chờ. Một ước lượng ban đầu cho phần dữ liệu từ các nhánh đang hoạt động là concurrency nhân với prefetch; đây chỉ là ước lượng, vì còn có hàng đợi ở upstream, publishOn và các toán tử khác.

Nếu downstream xử lý chậm, tăng concurrency và prefetch cùng lúc có thể làm bộ nhớ tăng nhanh. Hãy điều chỉnh từng tham số và đo số phần tử đang chờ, độ trễ cùng throughput.

Các toán tử khác cũng có tham số prefetch:

~~~java
import reactor.core.publisher.Flux;

Flux<Receipt> ordered = orderIds
    .flatMapSequential(
        id -> paymentClient.charge(id),
        8,
        16
    );
~~~

`flatMapSequential` cho phép xử lý các Publisher con đồng thời nhưng phát kết quả theo thứ tự nguồn. Việc giữ thứ tự có thể khiến kết quả của nhánh hoàn tất sớm phải chờ nhánh trước đó; hàng đợi kết quả vì vậy cần được tính đến khi chọn concurrency và prefetch.

Với `concatMap`, các Publisher con được xử lý tuần tự; tham số prefetch điều khiển lượng phần tử từ nguồn được yêu cầu trước trong quá trình chờ xử lý. Chọn toán tử theo yêu cầu thứ tự và mức độ song song trước khi tinh chỉnh prefetch.

## 6. Gom phần tử thành batch bằng buffer

Nếu dịch vụ đích hỗ trợ ghi nhiều bản ghi trong một lần gọi, chỉ chia demand thành lô vẫn chưa đủ. Ta cần gom các phần tử thành một collection để gửi theo batch.

`buffer(n)` gom tối đa `n` phần tử thành một danh sách rồi phát danh sách đó:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;

Flux<List<OrderEvent>> batches = eventSource.events()
    .buffer(100);
~~~

Với nguồn có đủ dữ liệu, downstream nhận các danh sách gồm 100 sự kiện. Nếu nguồn hoàn tất khi batch cuối chưa đủ 100 phần tử, `buffer(100)` vẫn phát batch cuối chứa các phần tử còn lại.

Nếu cần phát batch khi đạt kích thước hoặc khi đã chờ quá lâu, dùng `bufferTimeout`:

~~~java
import java.time.Duration;
import java.util.List;
import reactor.core.publisher.Flux;

Flux<List<OrderEvent>> batches = eventSource.events()
    .bufferTimeout(100, Duration.ofMillis(250));
~~~

Toán tử này phát batch khi đạt 100 phần tử hoặc khi hết 250 ms. Nó giúp tránh việc batch nhỏ phải chờ quá lâu khi lưu lượng thấp.

Có thể kết hợp với ghi dữ liệu bất đồng bộ:

~~~java
import java.time.Duration;
import java.util.List;
import reactor.core.publisher.Flux;

Flux<Void> writes = eventSource.events()
    .bufferTimeout(100, Duration.ofMillis(250))
    .filter(batch -> !batch.isEmpty())
    .flatMap(
        batch -> repository.saveAll(batch),
        4,
        1
    );
~~~

Trong ví dụ, mỗi batch có tối đa 100 sự kiện; tối đa bốn thao tác ghi batch chạy đồng thời. Prefetch của mỗi Publisher ghi được đặt là 1 vì mỗi batch được xem như một đơn vị công việc. Cần điều chỉnh concurrency theo giới hạn connection pool và khả năng chịu tải của cơ sở dữ liệu.

Lưu ý: `buffer` thay đổi kiểu phần tử downstream từ `OrderEvent` thành `List<OrderEvent>`. Nó không thay thế demand protocol. Backpressure vẫn truyền qua toán tử, còn việc giữ batch trong bộ nhớ là một phần chi phí cần tính toán.

## 7. Chọn kích thước batch theo độ trễ và năng lực xử lý

Không có một batch size phù hợp cho mọi nguồn và mọi hệ thống. Batch nhỏ giúp giảm độ trễ và lượng dữ liệu phải giữ trong bộ nhớ, nhưng có thể làm tăng số lần gọi dịch vụ. Batch lớn giảm số lần gọi và thường cải thiện throughput, nhưng tăng thời gian chờ để gom đủ phần tử và tăng chi phí xử lý khi một batch thất bại.

| Kích thước batch | Lợi ích | Chi phí hoặc rủi ro |
|---|---|---|
| Nhỏ | Phản hồi nhanh, ít bộ nhớ cho mỗi batch, dễ thử lại phạm vi nhỏ. | Nhiều lần gọi, overhead giao tiếp cao. |
| Trung bình | Cân bằng throughput, độ trễ và bộ nhớ trong nhiều trường hợp. | Cần đo để tìm ngưỡng phù hợp. |
| Lớn | Giảm số lần gọi, tận dụng tốt thao tác bulk. | Tốn bộ nhớ, tăng độ trễ gom nhóm và chi phí retry. |

Một quy trình chọn batch size thực tế:

1. Bắt đầu với kích thước nhỏ, chẳng hạn 32 hoặc 64 phần tử.
2. Đo throughput, thời gian xử lý mỗi batch, độ trễ đầu cuối và số phần tử đang chờ.
3. Tăng batch size từng bước nếu overhead gọi dịch vụ chiếm tỷ lệ lớn và bộ nhớ còn dư.
4. Giảm batch size nếu độ trễ tăng, bộ nhớ tiến gần giới hạn hoặc một batch mất quá lâu để xử lý.
5. Kiểm tra lại khi lưu lượng, kích thước payload hoặc năng lực dịch vụ đích thay đổi.

Nên đặt giới hạn trên cho batch size. Một batch có số lượng phần tử cố định vẫn có thể chiếm nhiều bộ nhớ nếu mỗi phần tử chứa payload lớn. Trong trường hợp đó, cần cân nhắc giới hạn theo tổng byte hoặc kích thước payload, ngoài giới hạn số phần tử.

## 8. Điều chỉnh batch size theo tải

Batch size có thể được điều chỉnh theo trạng thái hệ thống thay vì dùng một con số cố định. Ví dụ, hệ thống có thể giảm batch khi độ trễ cơ sở dữ liệu tăng và tăng dần khi dịch vụ hoạt động ổn định.

Một chính sách đơn giản có thể dùng ba mức:

| Tình trạng quan sát | Batch size gợi ý |
|---|---:|
| Độ trễ thấp, queue ngắn, CPU và connection pool còn dư | 128 |
| Độ trễ bình thường, tải vừa | 64 |
| Độ trễ cao hoặc queue tăng liên tục | 16 |

Các con số chỉ minh họa cách thiết kế chính sách; cần đo trong môi trường thực tế trước khi áp dụng.

Ví dụ, một bộ điều khiển có thể chọn kích thước batch kế tiếp dựa trên độ trễ xử lý batch vừa hoàn tất:

~~~java
import java.time.Duration;

final class BatchSizer {
    private int current = 64;

    int nextBatchSize(Duration lastBatchLatency) {
        if (lastBatchLatency.compareTo(Duration.ofSeconds(1)) > 0) {
            current = Math.max(16, current / 2);
        } else if (lastBatchLatency.compareTo(Duration.ofMillis(200)) < 0) {
            current = Math.min(128, current + 16);
        }

        return current;
    }
}
~~~

Đây là chính sách điều khiển đơn giản, chưa phải thuật toán tối ưu. Trong hệ thống thật, nên sử dụng nhiều tín hiệu thay vì chỉ đo thời gian một batch:

- Độ trễ p95 hoặc p99 của thao tác đích.
- Độ dài hàng đợi và số phần tử đang chờ.
- Tỷ lệ lỗi, timeout và retry.
- Mức sử dụng CPU, heap và connection pool.
- Throughput đầu vào so với throughput xử lý.

Cần tránh thay đổi batch size quá thường xuyên vì nó có thể làm hệ thống dao động. Có thể dùng khoảng thời gian đánh giá, giới hạn mức tăng giảm mỗi lần và hysteresis để chính sách ổn định hơn.

Reactor không tự động thay đổi batch size theo các metric trên. Ứng dụng phải xây dựng chính sách thích nghi và kết nối nó với cách phát demand hoặc cách gom batch. Ví dụ, một Subscriber tùy chỉnh có thể dùng `BatchSizer` để chọn số phần tử yêu cầu tiếp theo; một pipeline gom nhóm có thể chọn cấu hình batch theo từng giai đoạn hoặc từng partition.

## 9. Phối hợp batch demand, prefetch và buffering

Một pipeline có thể có nhiều tầng cùng giữ dữ liệu:

~~~mermaid
flowchart LR
    A["Publisher nguồn"] --> B["limitRate: chia request"]
    B --> C["publishOn: prefetch queue"]
    C --> D["bufferTimeout: gom batch"]
    D --> E["flatMap: concurrency + prefetch"]
    E --> F["Subscriber / dịch vụ đích"]
~~~

Mỗi tầng có một mục đích:

- `limitRate` điều tiết lượng demand truyền lên upstream.
- `publishOn` nạp trước dữ liệu và chuyển thực thi sang scheduler khác.
- `bufferTimeout` gom các phần tử thành batch để downstream xử lý theo nhóm.
- `flatMap` điều khiển số Publisher con hoạt động đồng thời và lượng dữ liệu yêu cầu trước từ mỗi nhánh.

Các hàng đợi của những tầng này có thể cộng dồn. Ví dụ, nếu `publishOn` đã nạp trước dữ liệu rồi `bufferTimeout` tiếp tục giữ phần tử để chờ đủ batch, tổng số phần tử đang nằm trong pipeline có thể lớn hơn một tham số prefetch đơn lẻ.

Khi phân tích bộ nhớ, cần tính đến:

- Số phần tử trong hàng đợi của từng toán tử.
- Số batch đang chờ ghi.
- Số thao tác ghi đang hoạt động và số phần tử mỗi batch.
- Kích thước trung bình và kích thước lớn nhất của một phần tử.
- Số subscriber hoặc partition đang chạy song song.

Backpressure giúp giới hạn lượng dữ liệu được yêu cầu qua giao thức, nhưng không bảo đảm mọi hàng đợi trong ứng dụng đều có kích thước cố định. Một toán tử có thể chủ động buffer, một nguồn nóng có thể có chính sách riêng, hoặc một tầng ngoài Reactive Streams có thể tích lũy dữ liệu. Cần kiểm tra toàn bộ pipeline và ranh giới tích hợp.

## 10. Kiểm thử hành vi request và batch

Có thể dùng `StepVerifier` để kiểm tra số phần tử và hành vi hoàn tất. Với Publisher tùy chỉnh hoặc `TestPublisher`, có thể quan sát việc Subscriber yêu cầu dữ liệu theo lô.

Ví dụ kiểm tra batch từ `buffer`:

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void bufferGomPhanTuThanhCacLo() {
    StepVerifier.create(Flux.range(1, 5).buffer(2))
        .expectNext(List.of(1, 2))
        .expectNext(List.of(3, 4))
        .expectNext(List.of(5))
        .verifyComplete();
}
~~~

Kiểm thử xác nhận batch cuối được phát khi nguồn hoàn tất dù chỉ có một phần tử.

Có thể kiểm tra thời gian phát batch bằng `bufferTimeout` với virtual time:

~~~java
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void bufferTimeoutPhatBatchKhiHetThoiGian() {
    StepVerifier.withVirtualTime(() ->
            Flux.concat(
                Flux.just(1, 2),
                Flux.never()
            ).bufferTimeout(3, Duration.ofSeconds(1))
        )
        .thenAwait(Duration.ofSeconds(1))
        .expectNext(List.of(1, 2))
        .thenCancel()
        .verify();
}
~~~

Nguồn phát hai phần tử rồi giữ mở. Vì batch chưa đủ ba phần tử, `bufferTimeout` phát danh sách sau khi hết một giây. Virtual time giúp kiểm thử mà không phải chờ thời gian thực.

Khi cần kiểm tra demand chính xác, có thể dùng một Subscriber tùy chỉnh hoặc `BaseSubscriber` ghi lại các lần gọi request. Cũng có thể dùng `TestPublisher` để điều khiển lúc phát dữ liệu và xác minh downstream không nhận vượt quá demand.

Các trường hợp nên có trong bộ kiểm thử:

- Batch đầy được phát ngay khi đạt kích thước tối đa.
- Batch cuối chưa đầy được phát khi nguồn hoàn tất.
- Batch được phát khi timeout dù chưa đủ kích thước.
- Cancellation từ downstream dừng việc gom batch và truyền yêu cầu hủy lên upstream.
- Lỗi upstream được truyền hoặc xử lý theo chính sách đã chọn.
- Concurrency giới hạn số thao tác batch đang hoạt động.
- Kích thước batch thích nghi không vượt giới hạn tối thiểu và tối đa đã đặt.

## 11. Cách lựa chọn cơ chế phù hợp

Khi thiết kế pipeline, hãy bắt đầu từ câu hỏi cần giải quyết:

| Nhu cầu | Cơ chế nên xem xét |
|---|---|
| Muốn yêu cầu upstream theo từng đợt | `BaseSubscriber` với `request(n)` hoặc `limitRate` |
| Muốn nạp sẵn dữ liệu giữa các scheduler | `publishOn(..., prefetch)` |
| Muốn xử lý nhiều Publisher con đồng thời | `flatMap(mapper, concurrency, prefetch)` |
| Muốn gom nhiều phần tử thành một collection | `buffer(n)` |
| Muốn gom theo kích thước hoặc thời gian | `bufferTimeout(n, duration)` |
| Muốn giới hạn số phần tử đang được yêu cầu | Demand có giới hạn và các toán tử backpressure phù hợp |
| Muốn batch thích nghi theo tải | Chính sách điều khiển của ứng dụng dựa trên metric |

Yêu cầu theo lô, prefetch và buffering là ba công cụ bổ sung cho nhau. `request(n)` quyết định Subscriber cho phép phát bao nhiêu phần tử; prefetch giúp toán tử chuẩn bị dữ liệu để pipeline ít phải chờ; buffering gom nhiều phần tử thành một đơn vị công việc. Điều chỉnh batch size cần dựa trên throughput, độ trễ và giới hạn bộ nhớ của toàn pipeline.

Trong hệ sinh thái Java reactive, phối hợp đúng các cơ chế này giúp xử lý nhiều sự kiện hiệu quả mà vẫn giữ quyền kiểm soát lượng dữ liệu đang đi qua hệ thống. Đây là một phần quan trọng của việc thiết kế pipeline Mono và Flux có backpressure rõ ràng, có thể quan sát và điều chỉnh theo tải thực tế.

