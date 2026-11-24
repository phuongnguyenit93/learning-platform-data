# Ảnh hưởng của prefetch, bộ đệm và mức xử lý đồng thời

Trong pipeline RSocket dùng Reactor, tốc độ dữ liệu đi qua hệ thống chịu ảnh hưởng của ba nhóm cấu hình: **prefetch** quyết định một operator chủ động yêu cầu trước bao nhiêu phần tử; **buffer** giữ dữ liệu khi producer và consumer lệch tốc độ hoặc khi cần gom lô; **concurrency** quyết định có bao nhiêu tác vụ hoặc publisher con được xử lý cùng lúc. Ba yếu tố này có thể tăng throughput, nhưng nếu đặt quá cao sẽ làm tăng bộ nhớ, độ trễ, số tác vụ đang chờ và áp lực lên database hoặc dịch vụ phụ thuộc.

RSocket có flow control ở cấp stream, còn Reactor có các operator điều tiết demand và hàng đợi nội bộ. Khi kết hợp chúng, cần hiểu prefetch của Reactor không phải quota request và cũng không phải giới hạn số stream trên connection. Bài này phân tích cách các cơ chế tương tác, cách ước lượng bộ nhớ, chọn cấu hình theo workload và kiểm thử để tìm điểm cân bằng.

## 1. Ba khái niệm cần phân biệt

| Khái niệm | Câu hỏi được trả lời | Phạm vi |
| --- | --- | --- |
| Prefetch | Operator sẽ yêu cầu trước bao nhiêu phần tử từ upstream? | Subscription và operator trong pipeline reactive. |
| Buffer | Có thể giữ bao nhiêu phần tử đang chờ hoặc gom thành một lô? | Operator, stream, connection hoặc ứng dụng tùy nơi đặt. |
| Concurrency | Có bao nhiêu publisher con/tác vụ được phép chạy cùng lúc? | Một pipeline hoặc limiter theo route, connection, tenant hay server. |

Ví dụ, một server nhận telemetry từ RSocket:

- Prefetch 32 khiến operator yêu cầu trước một nhóm phần tử để giảm thời gian chờ giữa các lần request.
- Buffer 256 giữ tối đa 256 event khi downstream tạm thời xử lý chậm, tùy loại operator và chính sách overflow.
- Concurrency 8 cho phép tối đa tám tác vụ ghi dữ liệu chạy đồng thời trong pipeline đó.

Các con số này có quan hệ với nhau nhưng không thay thế nhau. Tăng prefetch không tự tăng số tác vụ xử lý đồng thời; tăng concurrency không bảo đảm upstream có đủ demand; tăng buffer chỉ kéo dài thời gian hệ thống chịu được chênh lệch tốc độ trước khi phải giảm tốc hoặc từ chối dữ liệu.

## 2. RSocket demand và Reactor prefetch

RSocket hỗ trợ flow control theo stream. Với request-stream, requester gửi số payload response ban đầu mà nó sẵn sàng nhận trong frame request. Khi đã tiêu thụ một phần demand, requester có thể gửi frame **REQUEST_N** để yêu cầu thêm payload. Request-channel có flow control cho cả hai hướng dữ liệu.

Reactor cũng dùng hợp đồng Reactive Streams: subscriber gọi request(n) trên subscription để yêu cầu n phần tử. Các operator có thể chia, trì hoãn hoặc gộp các yêu cầu đó. Prefetch là mức demand mà một operator chủ động yêu cầu upstream để có dữ liệu sẵn trong hàng đợi nội bộ.

~~~mermaid
sequenceDiagram
    participant D as Downstream subscriber
    participant O as Reactor operator
    participant U as Upstream / RSocket source
    D->>O: request(10)
    O->>U: request(prefetch = 32)
    U-->>O: Emit các phần tử theo demand
    O-->>D: Phát tối đa 10 phần tử theo demand downstream
    Note over O: Giữ phần tử đã prefetch trong queue nội bộ
    D->>O: request(10) tiếp theo
    O->>U: Replenish demand khi queue xuống ngưỡng
~~~

Trong pipeline RSocket, demand từ Reactor cuối cùng có thể được ánh xạ thành các frame REQUEST_N trên stream. Tuy nhiên, số prefetch của một operator là chính sách cục bộ trong pipeline; nó không thay đổi giao thức RSocket thành một quota toàn connection.

## 3. Prefetch hoạt động như thế nào?

Prefetch thường được dùng bởi operator có queue hoặc xử lý bất đồng bộ, ví dụ:

- **publishOn(scheduler, prefetch):** chuyển xử lý downstream sang scheduler khác và dùng queue để giữ các phần tử đã yêu cầu từ upstream.
- **flatMap(mapper, concurrency, prefetch):** giới hạn số publisher con đang hoạt động và mức prefetch cho mỗi publisher con.
- **flatMapSequential(mapper, concurrency, prefetch):** cho phép xử lý publisher con đồng thời nhưng phát kết quả theo thứ tự nguồn.
- **concatMap(mapper, prefetch):** chỉ xử lý một publisher con tại một thời điểm, nhưng vẫn có thể prefetch phần tử nguồn để giảm khoảng trống giữa các lần xử lý.

Prefetch lớn có thể giảm thời gian chờ dữ liệu giữa các tác vụ và tăng throughput khi upstream có độ trễ. Đổi lại, operator có thể giữ nhiều phần tử hơn trong queue, làm tăng memory và thời gian dữ liệu nằm trong hệ thống.

Prefetch nhỏ giảm lượng dữ liệu được giữ trước và có thể giảm latency của từng phần tử, nhưng upstream có thể thường xuyên phải chờ yêu cầu mới. Với nguồn có round-trip hoặc chi phí lấy dữ liệu cao, prefetch quá nhỏ làm throughput giảm.

Không có một giá trị tối ưu chung. Hãy đo theo kích thước payload, độ trễ upstream, tốc độ downstream và số stream đồng thời.

## 4. Prefetch không phải concurrency

Trong flatMap, hai tham số thường được nhìn cùng nhau:

~~~java
Flux<StoredEvent> stored = incomingEvents.flatMap(
    event -> eventStore.append(event),
    12,  // concurrency: tối đa 12 publisher con hoạt động
    8    // prefetch: số phần tử yêu cầu trước cho mỗi inner publisher
);
~~~

Concurrency giới hạn số publisher con đang được subscribe đồng thời. Prefetch kiểm soát lượng demand được yêu cầu trước ở các publisher con. Nếu mỗi inner publisher là một Mono ghi database, concurrency gần với số thao tác ghi đang chạy cùng lúc; prefetch vẫn là chính sách yêu cầu dữ liệu của operator.

Với nguồn có nhiều phần tử, tăng concurrency thường giúp che giấu latency I/O vì trong khi một thao tác chờ database, các thao tác khác có thể tiến triển. Nhưng nếu concurrency vượt xa connection pool, phần lớn tác vụ chỉ chờ lấy connection. Hàng đợi chuyển từ Reactor sang pool database mà không làm throughput thực tăng lên.

## 5. Buffer có nhiều vai trò khác nhau

Không phải mọi buffer đều có cùng ngữ nghĩa:

| Loại buffer | Mục đích | Hệ quả |
| --- | --- | --- |
| Queue nội bộ của publishOn/flatMap | Tách producer và consumer, hỗ trợ prefetch/concurrency. | Giữ phần tử đang chờ xử lý hoặc phát xuống. |
| onBackpressureBuffer | Đệm khi upstream phát nhanh hơn downstream trong phạm vi capacity. | Có thể làm upstream tiếp tục phát trong khi queue tăng. |
| buffer(n) | Gom n phần tử thành một batch. | Giảm số lần gọi downstream nhưng chờ đủ batch hoặc tín hiệu flush. |
| Buffer ở transport | Giữ byte/frame đang chờ đọc hoặc ghi. | Tốn direct memory và ảnh hưởng write latency. |
| Buffer ở ứng dụng | Queue lệnh hoặc event để xử lý sau. | Cần capacity, overflow policy, expiry và metric riêng. |

Phải xác định buffer đang nằm ở lớp nào và ai chịu trách nhiệm giải phóng nó. Một queue trong operator, một buffer Netty và một queue nghiệp vụ có thể cùng tồn tại trên một payload; tổng memory có thể lớn hơn nhiều so với một con số buffer đơn lẻ.

## 6. Buffer batch khác buffer chống backpressure

Operator buffer(n) gom phần tử thành danh sách:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;

Flux<List<T>> batches = events.buffer(100);
~~~

Downstream chỉ nhận một batch khi đủ 100 phần tử hoặc khi nguồn hoàn tất. Cách này hữu ích khi ghi database theo batch hoặc gửi một request bulk. Tuy nhiên, nếu lưu lượng thấp, batch có thể chờ lâu; nếu payload lớn, batch giữ nhiều object trong heap.

Có thể đặt cả giới hạn số phần tử và thời gian:

~~~java
import java.time.Duration;
import java.util.List;
import reactor.core.publisher.Flux;

Flux<List<TelemetryEvent>> batches =
    events.bufferTimeout(100, Duration.ofMillis(200));
~~~

Batch được phát khi đủ 100 phần tử hoặc khi hết 200 ms. Giá trị cần cân bằng chi phí mỗi lần ghi với độ trễ chấp nhận được. Buffer batch làm thay đổi hình dạng dữ liệu từ T thành List<T>; nó không tương đương với queue giữ từng phần tử khi downstream thiếu demand.

## 7. onBackpressureBuffer và chính sách overflow

onBackpressureBuffer có thể giữ phần tử khi downstream tiêu thụ chậm. Nếu dùng overload có capacity, queue bị giới hạn và ứng dụng phải quyết định hành vi khi đầy:

~~~java
import reactor.core.publisher.BufferOverflowStrategy;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

Flux<ProcessedEvent> processed = source
    .onBackpressureBuffer(
        256,
        dropped -> metrics.incrementBufferOverflow(),
        BufferOverflowStrategy.ERROR
    )
    .publishOn(Schedulers.parallel(), 32)
    .map(this::transform);
~~~

Trong ví dụ, queue có giới hạn 256 phần tử. Khi đầy, pipeline báo overflow theo chiến lược ERROR; callback giúp ghi metric. Hành vi cụ thể phải phù hợp với loại dữ liệu:

- **ERROR:** overflow strategy của onBackpressureBuffer; phát lỗi khi buffer đầy.
- **DROP_OLDEST:** bỏ phần tử cũ nhất trong queue để nhận phần tử mới.
- **DROP_LATEST:** bỏ phần tử mới đến khi queue đã đầy.
- **onBackpressureDrop():** operator riêng bỏ các phần tử được phát khi downstream chưa có demand.
- **onBackpressureLatest():** operator riêng chỉ giữ phần tử mới nhất khi downstream chưa có demand.

onBackpressureBuffer chủ động yêu cầu upstream không giới hạn (Long.MAX_VALUE), rồi đệm ở local khi downstream chưa có demand. Vì vậy, operator này làm suy yếu backpressure truyền ngược tới nguồn trong lúc buffer còn nhận dữ liệu. Không đặt buffer không giới hạn trên luồng realtime chỉ để tránh lỗi; khi consumer chậm kéo dài, memory vẫn tăng cho tới khi process gặp áp lực nghiêm trọng.

Nếu dữ liệu quan trọng không được phép mất, cần một nguồn bền vững như broker hoặc log có replay, thay vì dựa vào queue trong heap.

## 8. limitRate điều tiết demand theo lô

limitRate chia một request lớn từ downstream thành các request nhỏ hơn gửi upstream:

~~~java
Flux<Event> controlled = source.limitRate(64);
~~~

Với overload nhận high tide và low tide, có thể điều chỉnh ngưỡng bổ sung demand:

~~~java
Flux<Event> controlled = source.limitRate(64, 48);
~~~

High tide giới hạn lượng demand tối đa được gửi upstream trong một đợt. Low tide quyết định ngưỡng khi operator yêu cầu thêm phần tử để bổ sung lượng đã tiêu thụ; nếu không chỉ định, Reactor dùng ngưỡng mặc định theo phiên bản. Cơ chế này giúp điều tiết request theo lô và giảm số lần phát tín hiệu demand nhỏ.

limitRate không phải rate limiter theo thời gian. Nó không có nghĩa là 64 event mỗi giây; nó giới hạn số phần tử được yêu cầu trong từng đợt. Nếu cần giới hạn request/giây hoặc event/giây, phải dùng rate limiter có clock/token bucket riêng.

## 9. Ước lượng memory do prefetch và buffer

Một ước lượng sơ bộ cho số phần tử đang được giữ có thể dựa trên:

\[
N_{queued} \approx N_{streams} \times
(P_{publishOn} + C_{flatMap}\times P_{inner} + B_{explicit})
\]

Đây chỉ là mô hình gần đúng để nhận diện bậc độ lớn. Pipeline thực tế có thể có nhiều queue lồng nhau, queue theo subscriber, transport buffer, object overhead và payload đã giải mã. Không phải mọi operator đều giữ đúng một queue có capacity bằng tham số prefetch.

Ước lượng bộ nhớ:

\[
M_{queued} \approx N_{queued} \times S_{avg}
\]

Trong đó S_avg là kích thước trung bình của phần tử trong heap sau decode, gồm object graph và reference overhead, không chỉ số byte trên wire. Với payload chứa chuỗi, collection hoặc DTO lồng nhau, kích thước heap có thể lớn hơn payload serialized nhiều lần.

Ví dụ minh họa: 500 stream, mỗi stream có khoảng 32 phần tử ở queue publishOn, 8 inner publisher với prefetch 8 và thêm buffer ứng dụng 64 phần tử:

\[
N_{queued} \approx 500 \times (32 + 8\times8 + 64)
= 80{,}000
\]

Nếu mỗi phần tử chiếm trung bình 2 KiB trong heap, riêng các phần tử đang chờ có thể xấp xỉ 156 MiB, chưa tính queue object, transport buffer, connection state và dữ liệu đang xử lý. Con số này không phải dự đoán chính xác; dùng nó để thấy rằng cấu hình nhỏ trên một stream có thể trở thành lượng memory lớn khi nhân với hàng trăm hoặc hàng nghìn stream.

## 10. Tác động đến throughput và latency

Prefetch và concurrency có thể tăng throughput khi nguồn hoặc dependency có latency: hệ thống giữ đủ công việc sẵn sàng để worker không phải chờ dữ liệu mới. Batch buffer có thể giảm round-trip và chi phí mỗi lần ghi.

Nhưng khi queue tăng, latency đầu-cuối thường tăng vì một phần tử phải chờ lâu hơn trước khi được xử lý. Một pipeline có thể đạt throughput cao hơn trong ngắn hạn nhưng trả kết quả chậm hơn và có nhiều công việc đang nằm trong hệ thống.

Định luật Little mô tả quan hệ giữa số công việc trung bình trong hệ thống, throughput và thời gian lưu lại:

\[
L = \lambda W
\]

L là số công việc trung bình đang ở trong hệ thống, λ là throughput trung bình và W là thời gian trung bình một công việc ở trong hệ thống. Nếu throughput không đổi mà queue L tăng, thời gian W cũng tăng. Vì vậy, không nên đánh giá cấu hình chỉ bằng số message/giây; cần đo latency p50/p95/p99 và queue depth cùng lúc.

## 11. Chọn concurrency theo downstream capacity

Concurrency nên được giới hạn theo tài nguyên thực sự xử lý công việc:

- Database connection pool và số query mà database chịu được.
- HTTP connection pool và giới hạn rate của dịch vụ ngoài.
- CPU core và thời gian xử lý thuần CPU.
- Broker partition/consumer concurrency.
- Bộ nhớ dành cho request đang hoạt động.

Ví dụ nếu một service có 20 database connection dành cho workload telemetry, bắt đầu với concurrency khoảng 16 hoặc 20 có thể hợp lý hơn 200. Sau đó đo throughput, thời gian chờ pool và latency database để điều chỉnh.

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Flux<WriteResult> persist(Flux<TelemetryEvent> events) {
    return events.flatMap(
        event -> Mono.fromCallable(() -> blockingDao.insert(event))
            .subscribeOn(Schedulers.boundedElastic()),
        16
    );
}
~~~

Ví dụ dùng tối đa 16 thao tác đồng thời. Vì mỗi inner publisher ở đây là Mono chỉ phát một kết quả, tham số prefetch của overload ba tham số không đem lại lợi ích đáng kể; tham số đó quan trọng hơn khi inner publisher là Flux có nhiều phần tử. Giá trị concurrency chỉ là điểm khởi đầu; cần căn chỉnh với pool và kiểm thử tải. Bounded elastic cô lập blocking thread nhưng không tạo thêm database connection.

## 12. Prefetch và concurrency trong các interaction RSocket

Các interaction RSocket có đặc tính khác nhau:

| Interaction | Vai trò của demand/prefetch | Lưu ý cấu hình |
| --- | --- | --- |
| Request-response | Một response; prefetch ít có ý nghĩa với chính response đơn lẻ. | Tập trung concurrency của request và latency dependency. |
| Fire-and-Forget | Không có response payload và không có flow-control demand từ responder cho request đó. | Client cần giới hạn tốc độ gửi; server cần admission/rate limit và queue hữu hạn. |
| Request-stream | Requester điều tiết response bằng demand; Reactor operator có thể prefetch để giữ queue local. | Cân bằng prefetch, số stream và kích thước payload. |
| Request-channel | Hai hướng dữ liệu có demand độc lập. | Theo dõi queue, prefetch và concurrency ở cả chiều gửi lẫn chiều nhận. |

Prefetch của một operator phía server không đồng nghĩa client đã yêu cầu vô hạn response. Demand vẫn được truyền qua các ranh giới reactive, nhưng operator có thể yêu cầu trước một phần dữ liệu để giữ queue của chính nó. Cần đo cả số phần tử đang được giữ tại server và client.

## 13. Request-channel: hai hướng, hai điểm nghẽn

Request-channel có thể nhận command từ requester và phát response từ responder đồng thời. Một bên xử lý command chậm có thể khiến queue đầu vào tăng; bên kia tiêu thụ response chậm có thể khiến queue đầu ra tăng.

Ví dụ:

~~~java
Flux<CommandResult> handle(Flux<DeviceCommand> commands) {
    return commands
        .limitRate(32)
        .flatMap(
            command -> commandService.apply(command),
            8,
            4
        );
}
~~~

Ở đây limitRate điều tiết demand upstream theo lô; flatMap cho phép tối đa tám command xử lý đồng thời và prefetch bốn phần tử cho mỗi inner publisher. Nếu cần giữ thứ tự command, thay flatMap bằng concatMap hoặc flatMapSequential tùy yêu cầu. Cần đánh giá riêng buffer của publisher command ở client và subscriber nhận CommandResult.

Không dùng một con số prefetch duy nhất để kết luận channel an toàn. Payload có kích thước khác nhau, hai chiều có tốc độ khác nhau và thời gian xử lý mỗi command có thể biến động.

## 14. Chọn overflow policy theo ý nghĩa dữ liệu

Khi buffer đầy, quyết định giữ hay bỏ dữ liệu phải dựa trên nghiệp vụ:

| Dữ liệu | Chính sách có thể phù hợp | Vì sao |
| --- | --- | --- |
| Telemetry đo liên tục, chỉ cần trạng thái mới nhất | LATEST hoặc coalesce theo key | Mẫu cũ có thể bị thay thế bởi mẫu mới. |
| Audit event hoặc giao dịch tài chính | ERROR/reject hoặc ghi vào durable broker | Không được âm thầm bỏ sự kiện. |
| Dashboard metrics có thể mất một số mẫu | DROP có metric cảnh báo | Ưu tiên hệ thống ổn định hơn lưu mọi mẫu. |
| Batch import có thể retry | Buffer hữu hạn và retry có giới hạn | Cần checkpoint để không mất hoặc nhân đôi batch. |
| Lệnh điều khiển thiết bị | Reject có phản hồi hoặc durable queue | Client phải biết lệnh có được tiếp nhận hay không. |

DROP hoặc LATEST không nên dùng cho command có side effect nếu client không nhận được thông tin lệnh đã bị bỏ. Với dữ liệu quan trọng, hãy dùng acknowledgement, event ID, idempotency và storage bền vững.

## 15. Pooled buffer và giải phóng tài nguyên

RSocket trên Reactor Netty có thể sử dụng pooled byte buffer để giảm cấp phát. Nếu ứng dụng chuyển đổi hoặc giữ reference tới DataBuffer, ByteBuf hay kiểu payload có ownership thủ công, cần hiểu quy tắc retain/release của thư viện.

Khi operator drop hoặc discard phần tử do overflow, cancellation hoặc filter, các pooled buffer có thể cần được giải phóng. Với kiểu dữ liệu hỗ trợ discard hook, có thể gắn doOnDiscard phù hợp để release tài nguyên. Không gọi release hai lần và không giữ reference sau khi buffer đã được trả về pool.

Nếu payload đã được decode thành DTO bất biến, vòng đời thường dễ quản lý hơn. Tuy nhiên, việc decode có thể làm tăng heap và giữ object graph lớn; cần cân bằng thời điểm decode với queue và concurrency.

## 16. Cấu hình theo từng workload

Không có một bộ thông số tối ưu cho tất cả route. Có thể bắt đầu từ các nguyên tắc:

| Workload | Prefetch | Buffer | Concurrency |
| --- | --- | --- | --- |
| Request-response truy vấn nhanh | Thấp hoặc mặc định | Nhỏ | Theo database/HTTP pool và SLA. |
| Telemetry stream liên tục | Vừa phải | Hữu hạn, có overflow policy | Theo tốc độ ingest và khả năng lưu trữ. |
| Batch write | Prefetch vừa phải | Batch theo count/time | Theo giới hạn database. |
| CPU-bound transform | Đủ để giữ worker bận | Queue hữu hạn | Gần số core hoặc theo benchmark. |
| Long-lived request-channel | Thận trọng, riêng từng chiều | Nhỏ/hữu hạn | Theo số channel và tài nguyên mỗi channel. |
| Event không được mất | Theo demand nguồn | Durable queue/broker thay vì heap buffer lớn | Theo khả năng consumer và replay. |

Hãy thay đổi từng tham số một trong benchmark để biết tác động của nó. Nếu cùng lúc tăng prefetch, buffer và concurrency, sẽ khó xác định yếu tố nào làm throughput tăng hoặc memory/latency xấu đi.

## 17. Kiểm thử và benchmark

Kiểm thử cần xác nhận cả demand, overflow, cancellation và giới hạn concurrency:

- Dùng StepVerifier với initial request nhỏ để xác nhận publisher không phát vượt demand.
- Kiểm tra limitRate chia request upstream thành các đợt như mong muốn.
- Đặt buffer capacity nhỏ, làm chậm downstream và xác nhận overflow policy.
- Đếm số inner publisher đồng thời để xác nhận flatMap không vượt concurrency.
- Hủy subscriber khi queue còn phần tử và xác nhận tài nguyên được giải phóng.
- Chạy nhiều RSocket stream đồng thời để đo tổng memory và số queue thực tế.
- Mô phỏng downstream chậm hoặc database pool cạn để quan sát queue depth và latency.
- Kiểm thử request-channel theo cả hai hướng, không chỉ response stream.

Ví dụ kiểm tra demand:

~~~java
import reactor.test.StepVerifier;

StepVerifier.create(source, 0)
    .thenRequest(2)
    .expectNext(event1, event2)
    .thenRequest(1)
    .expectNext(event3)
    .thenCancel()
    .verify();
~~~

Ví dụ này bắt đầu với demand bằng 0, yêu cầu hai phần tử rồi yêu cầu thêm một phần tử. Có thể dùng publisher test có ghi nhận request(n) để xác minh các lô demand upstream. Benchmark tải nên đo throughput, p50/p95/p99 latency, heap/direct memory, GC, queue depth, overflow count và downstream pool wait.

## 18. Quy trình tinh chỉnh có kiểm soát

Một quy trình thực tế:

1. Đo baseline với cấu hình mặc định: throughput, latency, memory và số stream.
2. Xác định dependency chậm nhất hoặc giới hạn tài nguyên đang bị chạm.
3. Đặt concurrency theo capacity của dependency, bắt đầu thấp hơn giới hạn pool một khoảng an toàn.
4. Điều chỉnh prefetch từng bước để giảm thời gian worker chờ dữ liệu mà không làm queue phình quá lớn.
5. Đặt buffer hữu hạn và chọn overflow policy dựa trên ý nghĩa dữ liệu.
6. Tăng số stream đồng thời trong khi quan sát memory và tail latency.
7. Kiểm thử cancellation, lỗi và reconnect vì queue có thể giữ dữ liệu qua thời điểm tải thay đổi.
8. Chọn cấu hình đáp ứng SLA ở tải bình thường và khi một dependency chậm, không chỉ ở peak throughput.

Nếu queue tăng liên tục dù throughput đã đạt giới hạn downstream, tăng prefetch hoặc buffer chỉ trì hoãn sự cố. Cần giảm đầu vào, tăng capacity downstream hoặc từ chối tải sớm.

## 19. Những lỗi thường gặp

**Nhầm prefetch với số stream đồng thời.** Prefetch là demand trước của operator; concurrency là số publisher con hoạt động. Cần điều chỉnh riêng.

**Tăng buffer không giới hạn để tránh overflow.** Queue lớn che giấu consumer chậm và có thể làm cạn heap/direct memory. Dùng capacity hữu hạn và overflow policy.

**Nhầm limitRate với rate limit theo giây.** limitRate chia demand thành lô; muốn giới hạn tốc độ theo thời gian cần rate limiter.

**Đặt concurrency vượt database pool.** Nhiều tác vụ chỉ chờ connection, tăng queue và latency mà không tăng throughput.

**Quên nhân buffer theo số stream.** Queue 256 phần tử trên một stream có thể trở thành hàng trăm nghìn phần tử khi có nhiều stream.

**Dùng buffer batch cho dữ liệu cần phản hồi tức thời.** buffer(n) có thể giữ phần tử cho tới khi đủ batch hoặc hết thời gian flush.

**Dùng DROP cho dữ liệu không được mất.** Command hoặc audit event cần acknowledgement/durable storage, không được âm thầm loại bỏ.

**Cho rằng RSocket demand và mọi queue Reactor là cùng một bộ đệm.** Demand là tín hiệu điều tiết; mỗi operator/transport có thể có queue riêng.

**Không kiểm tra cancellation và discard.** Khi stream bị hủy, phần tử đang đệm hoặc pooled buffer cần được giải phóng đúng cách.

## 20. Ghi nhớ

- Prefetch là số phần tử operator yêu cầu trước; buffer là nơi giữ phần tử; concurrency là số tác vụ/publisher con hoạt động đồng thời.
- RSocket REQUEST_N điều tiết demand ở stream; prefetch của Reactor là chính sách nội bộ có thể ảnh hưởng lượng demand truyền lên upstream.
- publishOn, flatMap, flatMapSequential và concatMap có queue/prefetch với vai trò khác nhau.
- onBackpressureBuffer cần capacity và overflow policy; queue không giới hạn có thể làm cạn bộ nhớ.
- buffer(n) gom batch và có thể tăng latency; bufferTimeout giúp flush theo count hoặc thời gian.
- limitRate chia demand thành lô, không phải giới hạn event mỗi giây.
- Ước lượng memory phải nhân queue/prefetch với số stream và kích thước object trong heap.
- Chọn concurrency theo database pool, HTTP pool, CPU và downstream capacity; không tăng chỉ để làm đầy worker.
- Request-channel có hai hướng demand và queue riêng; phải quan sát cả hai chiều.
- Chọn DROP/LATEST/ERROR/durable queue theo ý nghĩa nghiệp vụ của dữ liệu.
- Kiểm thử demand, overflow, concurrency, cancellation và tail latency dưới tải thực tế.
