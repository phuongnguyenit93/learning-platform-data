# Kiểm chứng tối ưu bằng đo đạc và giới hạn tài nguyên thực tế

Tối ưu một pipeline reactive chỉ có ý nghĩa khi kết quả được kiểm chứng bằng số liệu trong điều kiện tải đại diện. Một đoạn mã ít toán tử hơn chưa chắc chạy nhanh hơn; tăng concurrency có thể làm throughput tăng trong một khoảng nhưng cũng có thể khiến connection pool cạn, queue dài và độ trễ p99 tăng mạnh.

Trong Project Reactor, hiệu năng phụ thuộc đồng thời vào cách tổ chức Publisher, demand và backpressure, scheduler, số tác vụ đang chạy, kích thước dữ liệu, connection pool và năng lực của các dịch vụ phụ thuộc. Vì vậy, cần đo trước khi thay đổi, xác định giới hạn tài nguyên, rồi đo lại trên cùng workload để biết tối ưu có thực sự cải thiện hệ thống hay chỉ chuyển điểm nghẽn sang nơi khác.

## 1. Bắt đầu bằng giả thuyết và baseline

Không nên bắt đầu bằng việc tăng `flatMap` concurrency, đổi scheduler hoặc thêm cache theo cảm giác. Trước tiên hãy mô tả vấn đề có thể quan sát được:

- Throughput thấp hơn mục tiêu khi số request đồng thời tăng.
- Độ trễ p95 hoặc p99 vượt SLO dù độ trễ trung bình vẫn thấp.
- CPU thấp nhưng request chờ lâu, có thể do connection pool hoặc dịch vụ ngoài.
- CPU cao và thời gian xử lý tăng theo kích thước payload.
- Heap hoặc số lượng object chờ tăng theo thời gian.
- Scheduler có nhiều task pending hoặc queue của client tăng.
- Tỷ lệ timeout, retry hoặc cancellation tăng khi tải vượt một ngưỡng.

Sau đó đặt giả thuyết có thể kiểm chứng. Ví dụ: “Tăng concurrency của lời gọi inventory từ 8 lên 16 sẽ tăng throughput vì pool còn capacity, nhưng p99 không vượt 500 ms và số pending acquire không tăng liên tục.”

Baseline cần ghi lại cấu hình, phiên bản ứng dụng, JVM, CPU/memory limit, số instance, connection pool, scheduler, dữ liệu thử và mô hình tải. Nếu không giữ các yếu tố này ổn định, rất khó biết thay đổi nào tạo ra khác biệt.

Một lần đo nên trả lời ba câu hỏi: hệ thống đang xử lý bao nhiêu công việc, mỗi công việc mất bao lâu, và tài nguyên nào đang giới hạn tốc độ.

## 2. Đo đúng chỉ số: throughput, latency và tail latency

Throughput và latency mô tả hai mặt khác nhau của hiệu năng:

- **Throughput:** số request hoặc event hoàn tất trong một đơn vị thời gian, ví dụ requests/second.
- **Latency:** thời gian từ lúc nhận request đến khi có kết quả.
- **Tail latency:** các percentile cao như p95, p99 hoặc p99.9, phản ánh trải nghiệm của nhóm request chậm nhất.

Không nên chỉ báo cáo latency trung bình. Nếu phần lớn request mất 30 ms nhưng một nhóm nhỏ phải chờ 2 giây, average có thể che khuất vấn đề ảnh hưởng đến người dùng.

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| Requests/sec hoặc events/sec | Hệ thống hoàn tất được bao nhiêu công việc? |
| p50 | Trải nghiệm điển hình ở mức trung vị là gì? |
| p95 / p99 | Nhóm request chậm có vượt SLO không? |
| Error rate | Bao nhiêu request thất bại hoặc timeout? |
| In-flight requests | Có bao nhiêu request đang hoạt động cùng lúc? |
| Queue depth / pending acquire | Công việc đang chờ ở tầng nào? |
| CPU, heap, allocation, GC | Chi phí tính toán và quản lý bộ nhớ ra sao? |
| Active/pending connections | Pool có đủ connection hay đã trở thành nút thắt? |

Đo thời gian ở đúng ranh giới. Ví dụ, timer quanh toàn bộ request cho biết latency end-to-end; timer quanh lời gọi inventory cho biết riêng thời gian phụ thuộc đó. Hai phép đo này giúp phân biệt thời gian xử lý nội bộ với thời gian chờ mạng hoặc database.

Nếu có retry, cần đo cả thời gian của một lần thử và thời gian tổng của request. Một request thành công sau ba lần retry vẫn có thể vi phạm SLO dù mỗi lần gọi riêng lẻ khá nhanh.

## 3. Dùng benchmark và load test cho đúng mục tiêu

Benchmark vi mô và load test trả lời các câu hỏi khác nhau.

**Benchmark vi mô** phù hợp để so sánh chi phí của một đoạn xử lý hẹp, chẳng hạn biến đổi object, parser, hàm tính toán hoặc pipeline CPU-bound. Với Java, JMH giúp kiểm soát warmup, measurement iteration và fork để giảm sai lệch do JIT compiler.

~~~java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(2)
public class EventTransformBenchmark {
    private Event input;

    @Setup(Level.Trial)
    public void setup() {
        input = new Event("account-42", 1250);
    }

    @Benchmark
    public Event transform() {
        return transformEvent(input);
    }

    private Event transformEvent(Event event) {
        return new Event(event.accountId(), event.amount() * 2);
    }
}
~~~

Đoạn mã chỉ minh họa cấu hình JMH; `Event` và `transformEvent` là kiểu miền do ứng dụng định nghĩa. Nếu benchmark một pipeline Reactor đồng bộ, hãy tiêu thụ terminal result để công việc thực sự được thực hiện. Có thể dùng `block()` trong harness benchmark cô lập nếu cần lấy kết quả đồng bộ, nhưng không dùng cách đó trong event loop hoặc request path của ứng dụng.

**Load test** phù hợp để đánh giá hệ thống đầy đủ: HTTP server, scheduler, connection pool, database, network, retry và các service phụ thuộc. Nó cần payload và phân bố request gần với production, thời gian chạy đủ dài để phát hiện queue tăng hoặc rò rỉ tài nguyên, và mô hình tải được mô tả rõ.

Một load test nên ghi lại:

- Tốc độ gửi request và concurrency thực tế.
- Thời gian ramp-up, thời gian giữ tải ổn định và thời gian giảm tải.
- Phân bố payload, cache hit/miss và tỷ lệ lỗi dự kiến.
- Số instance, giới hạn CPU/memory và cấu hình pool.
- Throughput, latency percentiles, error rate và các chỉ số tài nguyên.

Không dùng benchmark vi mô để kết luận hệ thống có thể phục vụ bao nhiêu request mỗi giây. Ngược lại, nếu load test cho thấy toàn bộ request chậm, benchmark một hàm nhỏ có thể giúp xác định liệu một đoạn CPU transform có đáng kể hay không.

## 4. Tránh kết luận từ một lần chạy

Kết quả đo có thể bị ảnh hưởng bởi JIT warmup, GC, cache lạnh, DNS, kết nối mới, noisy neighbor hoặc tải nền. Để so sánh công bằng:

1. Chạy warmup trước khi lấy số liệu chính.
2. Giữ nguyên môi trường và dữ liệu giữa baseline với candidate.
3. Thay đổi một yếu tố chính mỗi lần để biết nguyên nhân.
4. Lặp lại nhiều lần và so sánh phân bố, không chỉ một con số.
5. Đo đủ lâu để hệ thống đạt trạng thái ổn định.
6. Ghi lại cả throughput, tail latency, lỗi và tài nguyên.
7. Kiểm tra sau khi ngừng tải xem queue, pool và heap có trở về mức bình thường không.

Dùng mô hình tải phù hợp với mục tiêu. Mô hình cố định concurrency cho biết hệ thống xử lý ra sao khi luôn có một số request đang hoạt động. Mô hình cố định arrival rate giúp kiểm tra hệ thống khi lưu lượng đến theo tốc độ định trước. Với hệ thống có tail latency cao, mô hình phát request phụ thuộc vào thời gian phản hồi trước đó có thể che khuất độ trễ do hiện tượng coordinated omission; cần chọn công cụ và cấu hình load generator để ghi nhận cả khoảng thời gian người dùng phải chờ.

Không tăng tải vô hạn chỉ để tìm con số throughput lớn nhất. Cần xác định điểm hệ thống bắt đầu vi phạm SLO hoặc cạn tài nguyên, rồi chọn mức vận hành có headroom.

## 5. Quan sát pipeline Reactor bằng metrics

Metrics giúp xác định thời gian và tài nguyên bị tiêu thụ ở đâu. Trong ứng dụng Spring, Micrometer thường được dùng để xuất metrics đến hệ thống giám sát.

Có thể đặt tên cho một đoạn pipeline và gắn metrics:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import reactor.core.publisher.Flux;
import reactor.core.observability.micrometer.Micrometer;

Flux<EnrichedEvent> measured =
    source
        .name("event-enrichment")
        .tag("stage", "enrich")
        .tap(Micrometer.metrics(registry))
        .map(this::enrich);
~~~

Đoạn mã cần phiên bản Reactor có tích hợp Micrometer tương ứng và dependency phù hợp. Có thể dùng instrumentation của framework hoặc Micrometer Observation nếu ứng dụng đã chuẩn hóa tracing và metrics theo cách đó.

Đặt metric ở các ranh giới có ý nghĩa: nhận request, gọi service ngoài, truy vấn database, transform CPU-bound và hoàn tất workflow. Không cần instrument từng operator nhỏ nếu số liệu không giúp quyết định.

Theo dõi ít nhất:

- Request rate, active request, completion và error.
- Thời gian xử lý ở từng dependency và toàn request.
- Retry, timeout, cancellation và fallback.
- Scheduler worker, task pending và queue nếu có thể quan sát.
- Connection pool: acquired, idle, pending acquire và acquire timeout.
- JVM: heap, allocation rate, GC pause, thread count và CPU.
- Queue hoặc buffer của tầng tích hợp và số phần tử đang in-flight.

Không tạo tag có cardinality cao như user ID, request ID hoặc order ID cho metric. Những giá trị đó phù hợp với log hoặc trace. Metric nên dùng tag có tập giá trị hữu hạn như tên operation, loại kết quả hoặc service đích.

## 6. Tìm nút thắt bằng cách ghép số liệu

Một chỉ số đơn lẻ hiếm khi đủ để kết luận. Hãy đọc các metric cùng nhau:

| Dấu hiệu | Khả năng cần kiểm tra |
|---|---|
| CPU cao, throughput không tăng | Transform CPU-bound, serialization, lock contention hoặc GC. |
| CPU thấp, latency cao, pending connection tăng | Connection pool hoặc database đang giới hạn. |
| Active request tăng và p99 tăng liên tục | Hệ thống nhận tải nhanh hơn khả năng hoàn tất; queue tích lũy. |
| Scheduler pending tăng | Công việc bị dồn vào scheduler hoặc có tác vụ blocking. |
| Heap tăng theo thời gian, GC thường xuyên | Buffer/cache không giới hạn, payload lớn hoặc tham chiếu bị giữ. |
| Retry và timeout cùng tăng | Dependency không ổn định hoặc concurrency vượt capacity. |
| Throughput ổn định nhưng error rate tăng | Đang chạm giới hạn hoặc một dependency bắt đầu từ chối request. |

Dùng Java Flight Recorder (JFR), GC log hoặc profiler như async-profiler để tìm CPU hotspot, allocation và lock. Heap dump hữu ích khi nghi ngờ object bị giữ lâu. Thread dump giúp nhận diện thread bị block hoặc pool cạn.

Với Reactor, có thể bật BlockHound trong môi trường test để phát hiện một số lời gọi blocking trên thread không được phép block:

~~~java
import reactor.blockhound.BlockHound;

@BeforeAll
static void installBlockHound() {
    BlockHound.install();
}
~~~

BlockHound không thay thế profiler hoặc load test. Nó giúp phát hiện một nhóm lỗi blocking, còn hiệu năng thực tế vẫn cần được đo dưới workload đại diện.

## 7. Đặt giới hạn concurrency theo capacity

`flatMap` cho phép giới hạn số Publisher con đang hoạt động trong một subscription:

~~~java
Flux<Inventory> inventories = productIds
    .flatMap(
        id -> inventoryClient.lookup(id),
        16,
        1
    );
~~~

Trong ví dụ, tối đa 16 Publisher con được subscribe đồng thời; tham số cuối điều khiển prefetch cho mỗi inner Publisher. Giá trị phù hợp phụ thuộc latency của service, connection pool, kích thước response và giới hạn phía server.

Không nên chọn concurrency chỉ dựa trên số CPU. Một lời gọi HTTP thường chờ I/O; giới hạn phù hợp có thể khác số core. Ngược lại, nếu mapper thực hiện CPU-bound work, tăng concurrency quá cao có thể tạo tranh chấp CPU và làm tail latency xấu hơn.

Cần tính cả concurrency giữa nhiều request. Nếu mỗi request có thể mở tối đa 16 lời gọi con và có 100 request đồng thời, hệ thống có thể tạo ra tới khoảng 1.600 lời gọi đang hoạt động ở tầng đó. Một giới hạn cục bộ trong `flatMap` không phải giới hạn toàn ứng dụng.

Có thể dùng bulkhead hoặc semaphore ở tầng client để đặt giới hạn dùng chung cho mọi request. Khi đã đạt giới hạn, hệ thống cần một chính sách rõ ràng: chờ trong queue có giới hạn, từ chối sớm, hoặc fallback theo nghiệp vụ.

## 8. Giới hạn scheduler và cô lập blocking work

Không chuyển mọi công việc sang `Schedulers.boundedElastic()` chỉ để “cho chạy nền”. Scheduler là tài nguyên hữu hạn và có queue; nếu tác vụ blocking đến nhanh hơn tốc độ hoàn tất, pending task vẫn tăng.

Với API blocking không thể thay thế ngay, tạo scheduler có giới hạn phù hợp:

~~~java
Scheduler legacyIo = Schedulers.newBoundedElastic(
    24,
    200,
    "legacy-io"
);

Mono<Customer> customer =
    Mono.fromCallable(() -> legacyClient.loadCustomer(customerId))
        .subscribeOn(legacyIo);
~~~

Các tham số giới hạn số worker và số task được xếp hàng theo API của Reactor. Hãy chọn dựa trên capacity của dịch vụ legacy, giới hạn thread của process và thời gian chờ cho phép. Khi ứng dụng dừng, dispose scheduler do ứng dụng tự tạo.

Với công việc CPU-bound, `Schedulers.parallel()` thường phù hợp hơn vì số worker gắn với năng lực CPU. Không chạy JDBC, file blocking hoặc lời gọi đồng bộ chậm trên scheduler CPU-bound hoặc event loop.

Một scheduler có queue hữu hạn giúp hệ thống từ chối hoặc bộc lộ overload sớm hơn. Queue vô hạn chỉ trì hoãn thời điểm thất bại và có thể làm heap tăng đến khi hệ thống không còn đáp ứng.

## 9. Giới hạn connection pool và pending acquire

Tăng `flatMap` concurrency mà không kiểm tra connection pool có thể chỉ làm nhiều request chờ lấy connection hơn. Khi pool đã đạt max connection, pending acquire tăng; latency end-to-end tăng dù CPU của ứng dụng vẫn thấp.

Với Reactor Netty, có thể cấu hình pool theo capacity và thời gian chờ:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("inventory")
        .maxConnections(80)
        .pendingAcquireMaxCount(160)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .build();

HttpClient httpClient = HttpClient.create(provider);

WebClient inventoryClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .baseUrl(inventoryBaseUrl)
    .build();
~~~

Đây là ví dụ cấu hình; cần thêm import và chọn giá trị theo giới hạn kết nối của service đích, số instance, timeout và tải thực tế. Nếu có 10 instance, mỗi instance mở tối đa 80 connection thì dependency có thể nhận đến 800 connection từ ứng dụng này.

`pendingAcquireMaxCount` giới hạn số request chờ connection. Khi hàng đợi đầy hoặc chờ quá lâu, lỗi acquire cần được quan sát và xử lý như một tín hiệu overload. Không tăng pool vô hạn để che một dependency có capacity thấp hơn.

Đặt timeout riêng cho connect, response và toàn request theo hợp đồng. Timeout quá dài giữ request và tài nguyên in-flight lâu; timeout quá ngắn làm retry tăng và có thể tạo thêm tải lên dependency đang yếu.

## 10. Backpressure và giới hạn queue

Backpressure cho phép downstream yêu cầu số phần tử mà nó có thể xử lý. Các nguồn và operator tuân theo demand có thể điều chỉnh tốc độ phát. Tuy nhiên, không phải mọi nguồn đều hỗ trợ backpressure; hot source, callback API hoặc message listener có thể cần buffer, drop hoặc pause/resume riêng.

Một test nhỏ có thể xác minh demand bằng `StepVerifier`:

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void downstreamChiNhanSoPhanTuDaRequest() {
    StepVerifier.create(Flux.range(1, 5), 0)
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(3)
        .expectNext(3, 4, 5)
        .verifyComplete();
}
~~~

Test bắt đầu với demand bằng 0, sau đó yêu cầu hai phần tử rồi ba phần tử. Nó kiểm tra giao thức demand của nguồn hữu hạn, nhưng không thay thế load test cho một nguồn ngoài thực tế.

Với nguồn không thể chậm lại, cần chọn chính sách rõ ràng. Ví dụ, buffer có giới hạn và phát lỗi khi vượt capacity:

~~~java
Flux<Event> bounded = hotSource
    .onBackpressureBuffer(
        256,
        dropped -> metrics.counter("events.buffer.overflow").increment(),
        BufferOverflowStrategy.ERROR
    );
~~~

Tùy nghiệp vụ, có thể chọn drop phần tử cũ, giữ giá trị mới nhất hoặc từ chối khi đầy. Không có chính sách chung cho mọi loại event: bỏ một telemetry sample có thể chấp nhận được, nhưng bỏ một lệnh thanh toán thì không.

`limitRate` điều chỉnh cách Reactor chia nhỏ request upstream; nó không phải bộ giới hạn tốc độ theo giây. Nếu cần rate limit theo thời gian, hãy dùng token bucket, limiter ở gateway hoặc cơ chế điều tiết phù hợp. Đừng nhầm demand batching với giới hạn requests/second.

## 11. Ước lượng bộ nhớ từ dữ liệu in-flight

Một pipeline có thể giữ dữ liệu ở nhiều vị trí: queue của scheduler, prefetch của operator, inner Publisher, connection response, buffer và cache. Bộ nhớ không chỉ phụ thuộc số request mà còn phụ thuộc kích thước payload và object graph.

Có thể dùng một ước lượng ban đầu:

`Bộ nhớ dữ liệu đang hoạt động ≈ số phần tử in-flight × kích thước giữ lại trung bình mỗi phần tử + overhead của queue và object`

Đây chỉ là ước lượng. Object graph có thể chia sẻ tham chiếu, payload có thể nén hoặc giữ buffer native, và mỗi operator có queue riêng. Hãy kiểm tra retained heap, allocation và direct memory bằng công cụ runtime.

Ví dụ, nếu 500 request cùng giữ response trung bình 200 KB, riêng payload đã có thể chiếm khoảng 100 MB trước khi tính object, buffer và queue khác. Đây là phép tính minh họa, không phải mức sử dụng dự đoán cho mọi JVM.

Các cách giảm memory pressure:

- Giới hạn concurrency và prefetch theo capacity.
- Dùng buffer có max size và chính sách overflow.
- Tránh `collectList()` trên nguồn không giới hạn.
- Cache theo size hoặc TTL có chủ đích.
- Giải phóng buffer/reference-counted resource khi bị discard.
- Chuyển payload lớn thành DTO nhỏ nếu downstream không cần toàn bộ object graph.
- Đo cả heap và direct/native memory khi dùng Netty.

## 12. Kiểm chứng tối ưu theo một quy trình lặp

Một vòng tối ưu có thể thực hiện như sau:

1. **Định nghĩa mục tiêu:** ví dụ p99 dưới 400 ms ở 300 request/second với error rate dưới 0,1%.
2. **Ghi baseline:** throughput, latency percentiles, lỗi, CPU, heap, GC, pending connection và queue.
3. **Xác định nút thắt:** dùng metrics, trace, JFR hoặc profiler để tìm tầng bị giới hạn.
4. **Đặt một giả thuyết:** ví dụ giảm prefetch để hạn chế số payload đang chờ.
5. **Thay đổi một yếu tố:** giữ nguyên các cấu hình khác.
6. **Chạy lại cùng workload:** warmup, ramp-up và thời gian đo như baseline.
7. **So sánh cả lợi ích và chi phí:** throughput, p99, error rate, CPU, memory và queue.
8. **Thử tải vượt mục tiêu:** xác định overload được kiểm soát hay queue tiếp tục tăng.
9. **Kiểm tra sau tải:** queue phải drain, connection được trả lại pool và heap ổn định theo đặc tính ứng dụng.

Bảng báo cáo nên lưu cả cấu hình lẫn kết quả:

| Phiên bản | Concurrency | Throughput | p95 | p99 | Error rate | CPU | Pending queue |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline | Ghi giá trị đo | Ghi giá trị đo | Ghi giá trị đo | Ghi giá trị đo | Ghi giá trị đo | Ghi giá trị đo | Ghi giá trị đo |
| Candidate | Ghi giá trị đo | Ghi giá trị đo | Ghi giá trị đo | Ghi giá trị đo | Ghi giá trị đo | Ghi giá trị đo | Ghi giá trị đo |

Không điền số liệu ước đoán vào báo cáo. Nếu throughput tăng nhưng p99 hoặc error rate vượt ngưỡng, candidate không đạt mục tiêu. Nếu latency giảm nhưng CPU hoặc memory vượt quota, cần đánh giá chi phí vận hành và headroom trước khi chấp nhận.

## 13. Kiểm tra hành vi khi quá tải

Một hệ thống khỏe không chỉ nhanh khi tải thấp; nó cần phản ứng có kiểm soát khi nhu cầu vượt capacity.

Hãy tăng tải từng bước và quan sát:

- Request có bị từ chối sớm khi bulkhead hoặc pool đầy không?
- Queue có giới hạn hay tăng liên tục?
- Timeout có xảy ra trước khi request giữ tài nguyên quá lâu không?
- Retry có làm tải lên dependency tăng thêm không?
- Cancellation có giải phóng connection và buffer không?
- Service có phục hồi sau khi giảm tải không?
- Một dependency chậm có làm cạn tài nguyên của các request không liên quan không?

Overload nên có tín hiệu rõ như lỗi 429/503, timeout có phân loại, metric overflow hoặc pending acquire. Một queue tăng không giới hạn khiến latency tiếp tục tăng và có thể dẫn đến memory exhaustion. Giới hạn tài nguyên giúp hệ thống từ chối một phần công việc để giữ khả năng phục vụ phần còn lại.

## 14. Checklist trước khi chấp nhận một tối ưu

- Có baseline và giả thuyết đo được không?
- Workload có phản ánh payload, tỷ lệ lỗi và concurrency thực tế không?
- Đã warmup và lặp phép đo trong cùng môi trường chưa?
- Có xem p95/p99 thay vì chỉ average không?
- Có đo throughput, error rate và cancellation cùng lúc không?
- Đã quan sát CPU, heap, allocation, GC và direct memory chưa?
- `flatMap` concurrency có phù hợp capacity của dependency không?
- Scheduler có giới hạn worker và queue không?
- Connection pool và pending acquire có giới hạn không?
- Buffer, prefetch và cache có chính sách size/TTL/overflow không?
- Backpressure có được kiểm chứng với demand thực tế không?
- Khi quá tải, hệ thống có từ chối hoặc giảm tải có kiểm soát không?
- Sau khi giảm tải, queue và resource có trở về trạng thái ổn định không?

Trong ứng dụng Java reactive, tối ưu chỉ được xác nhận khi số liệu chứng minh cải thiện trên workload đại diện và các giới hạn tài nguyên vẫn được tôn trọng. Hãy đo baseline, xác định nút thắt, thay đổi có giả thuyết, rồi đo lại throughput, tail latency, lỗi và mức tiêu thụ tài nguyên. `Mono`, `Flux`, scheduler và backpressure cung cấp công cụ điều phối; metrics, benchmark, load test và giới hạn capacity mới cho biết pipeline có đáp ứng được điều kiện vận hành thực tế hay không.

