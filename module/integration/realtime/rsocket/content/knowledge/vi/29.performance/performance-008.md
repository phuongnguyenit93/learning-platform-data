# Phân biệt điểm nghẽn mạng, CPU, GC, event loop và dịch vụ phụ thuộc

## Mục tiêu bài học

Khi một request RSocket phản hồi chậm, nguyên nhân có thể nằm trên đường truyền, trong code Java, ở bộ thu gom rác, tại event loop hoặc ở một dịch vụ mà handler gọi tiếp. Các nguyên nhân này có thể tạo ra cùng một triệu chứng là latency tăng, nhưng cách xác minh và xử lý rất khác nhau.

Sau bài này, bạn có thể:

- Đọc đường đi của một request RSocket từ client tới handler và dependency.
- Phân biệt dấu hiệu của network bottleneck, CPU saturation, GC pause, event-loop starvation và downstream latency.
- Kết hợp latency, throughput, CPU, GC, thread dump, event-loop metrics và distributed trace.
- Dùng JFR, `jcmd`, GC log và Reactor Netty metrics để thu thập bằng chứng.
- Offload blocking I/O và CPU-heavy work khỏi event loop đúng cách.
- Tránh tăng thread, connection hoặc heap khi chưa xác định nguyên nhân.
- Lập quy trình điều tra hiệu năng có thể lặp lại và kiểm chứng sau khi sửa.

## Đường đi của một request RSocket

Một request-response có thể đi qua nhiều chặng:

~~~mermaid
flowchart LR
    C[Client] --> N[Network / TCP / WebSocket]
    N --> E[Server event loop]
    E --> D[Decode data và metadata]
    D --> H[Spring handler]
    H --> X[CPU / business logic]
    X --> G[GC và memory allocation]
    X --> S[Downstream service / DB]
    S --> H
    H --> E
    E --> N
    N --> C
~~~

Tổng thời gian client quan sát có thể bao gồm:

- Thời gian truyền request và response qua mạng.
- Thời gian chờ event loop hoặc queue.
- Thời gian decode/encode payload và metadata.
- Thời gian xử lý nghiệp vụ trên CPU.
- Thời gian dừng ứng dụng do GC hoặc safepoint.
- Thời gian chờ database, cache, HTTP/RSocket service khác hoặc connection pool.

Một phép đo ở handler chỉ bao phủ một phần đường đi. Vì vậy, cần đo ở nhiều ranh giới để biết thời gian bị tiêu tốn ở đâu.

### Không nhầm các triệu chứng

| Dấu hiệu | Có thể gợi ý | Cần xác minh |
|---|---|---|
| Client latency cao, server handler latency thấp | Mạng, proxy, client hoặc serialization | RTT, retransmit, trace phía client/server |
| CPU process liên tục cao, một số method chiếm nhiều sample | CPU saturation | JFR execution samples, CPU profile |
| Latency tăng thành từng đợt trùng với GC pause | GC hoặc safepoint | GC log, JFR GC events |
| Event loop pending tasks tăng, nhiều connection cùng chậm | Event loop bị quá tải hoặc bị block | Thread dump, event-loop metrics |
| CPU/event loop bình thường nhưng thời gian chờ database/service tăng | Dependency bottleneck | Distributed trace, query/remote-service metrics |
| Throughput không tăng dù concurrency tăng, queue và latency tăng | Một tài nguyên đã bão hòa | CPU, pool wait, event loop, network, dependency |

Không kết luận chỉ từ một metric. Ví dụ CPU cao có thể do ứng dụng xử lý dữ liệu nặng hoặc do GC; latency cao có thể do mạng hoặc do handler chờ database. Hãy đối chiếu nhiều tín hiệu cùng thời điểm.

## Thiết lập baseline trước khi tối ưu

Trước khi thay đổi code hoặc cấu hình, ghi lại trạng thái hiện tại trong cùng một kịch bản tải:

- Request rate và số client đồng thời.
- p50, p95, p99 latency của request-response.
- Time-to-first-item và thời lượng của request-stream.
- Throughput payload inbound/outbound và kích thước payload.
- Error, timeout, retry và cancellation rate.
- Số connection và active stream.
- CPU process/container, heap, direct memory, GC pause và thread.
- Event loop pending tasks và thời gian chờ dependency.

Giữ ổn định dữ liệu đầu vào, số client, thời gian warm-up và thời gian đo. Nếu đổi nhiều biến cùng lúc, sẽ khó biết thay đổi nào thực sự cải thiện kết quả.

Với RSocket, connection có thể multiplex nhiều stream. Một connection đang mở không chứng minh handler có thể xử lý thêm request. Cũng không nên so sánh hai lần đo nếu một lần dùng request-response còn lần kia dùng request-stream dài hạn.

## Điểm nghẽn mạng (network bottleneck)

### Dấu hiệu thường gặp

Network bottleneck xảy ra khi dữ liệu mất nhiều thời gian trên đường truyền hoặc link không đáp ứng được lưu lượng. Một số dấu hiệu:

- Client latency cao nhưng server handler xử lý nhanh.
- RTT tăng, packet retransmission hoặc packet loss xuất hiện.
- Throughput đạt gần giới hạn băng thông của interface hoặc đường truyền.
- Connection reset, timeout hoặc WebSocket/TCP reconnect tăng.
- Latency tăng theo kích thước payload.
- Các service ở xa region hoặc đi qua nhiều proxy chậm hơn rõ rệt.

RSocket multiplex nhiều stream trên một TCP connection, nhưng TCP vẫn là byte stream có thứ tự. Packet loss có thể làm chậm dữ liệu phía sau trên cùng connection, kể cả khi các stream RSocket khác không liên quan về nghiệp vụ. Multiplexing ở tầng RSocket không loại bỏ TCP head-of-line blocking.

### Cách xác minh

1. Đo RTT giữa client và server trong cùng thời điểm có vấn đề.
2. Kiểm tra packet retransmission, dropped packets, socket send/receive queue và network interface errors.
3. So sánh request nhỏ và request lớn để xem latency tăng theo số byte hay không.
4. So sánh client cùng region với client ở region xa.
5. Kiểm tra proxy, load balancer, NAT, firewall và TLS termination.
6. Kiểm tra DNS/TLS handshake nếu thời gian chậm xảy ra chủ yếu lúc mở connection mới.

Trên Linux, có thể xem thông tin TCP của socket bằng:

~~~bash
ss -ti dst 10.0.2.15
~~~

Lệnh này giúp xem RTT, retransmission và một số thông tin TCP nếu kernel cung cấp. Có thể dùng `ping` hoặc `mtr` để khảo sát đường đi, nhưng ICMP có thể bị giới hạn hoặc ưu tiên khác với traffic ứng dụng. Kết quả ping không thay thế phép đo trên connection RSocket thật.

Trên Windows, có thể bắt đầu bằng:

~~~powershell
Get-NetTCPConnection -State Established
netstat -s
~~~

Các công cụ hệ điều hành chỉ cung cấp góc nhìn socket/network. Hãy ghép chúng với client-side latency và server-side handler latency.

### Hướng xử lý

- Giảm payload không cần thiết và tránh serialize dữ liệu thừa.
- Nén khi payload đủ lớn và chi phí CPU nén/giải nén thấp hơn chi phí mạng.
- Đặt client/service gần nhau hơn nếu RTT là nguyên nhân chính.
- Kiểm tra MTU, proxy timeout, socket buffer và network policy theo bằng chứng.
- Dùng stream để truyền dữ liệu theo phần thay vì gom một payload quá lớn.
- Giới hạn tốc độ gửi và tôn trọng backpressure khi consumer không theo kịp.

Không tăng số event loop để chữa RTT cao. Event loop không thể làm packet đi qua mạng nhanh hơn.

## Điểm nghẽn CPU (CPU saturation)

### Dấu hiệu thường gặp

- CPU process hoặc container gần giới hạn trong thời gian latency tăng.
- Throughput không tăng dù thêm client đồng thời.
- Runnable threads và CPU run queue tăng.
- JFR cho thấy một số method chiếm nhiều execution samples.
- CPU time cao ở JSON/CBOR codec, compression, encryption, validation, mapping hoặc thuật toán nghiệp vụ.
- p95/p99 tăng cùng CPU utilization; GC có thể là nguyên nhân phụ nếu allocation rate cao.

CPU cao không đồng nghĩa event loop bị block. Một tác vụ tính toán dài có thể chiếm CPU; một lời gọi blocking có thể làm event loop đứng chờ trong khi CPU lại thấp.

### Cách xác minh

Dùng JFR để lấy execution profile trong khoảng thời gian có tải đại diện. JFR ghi nhận execution samples, thread state, allocation và các sự kiện JVM; xem recording bằng Java Mission Control hoặc công cụ JFR.

Có thể bắt đầu recording từ JVM đang chạy:

~~~bash
jcmd <pid> JFR.start name=RSocketProfile settings=profile duration=2m filename=rsocket-profile.jfr
~~~

Sau khi recording hoàn tất:

~~~bash
jfr summary rsocket-profile.jfr
jfr print --events jdk.ExecutionSample rsocket-profile.jfr
~~~

Đọc các stack trace được sample nhiều nhất. Một method xuất hiện nhiều trong execution samples có thể là CPU hotspot, nhưng cần xem tổng thể và kiểm tra nó có thực sự nằm trên critical path của request hay không.

Nếu chạy trong container, kiểm tra cả CPU limit và CPU throttling. Một process có thể không dùng hết CPU của host nhưng vẫn bị giới hạn bởi quota của container.

### Hướng xử lý

- Giảm công việc lặp lại, copy dữ liệu và chuyển đổi object không cần thiết.
- Chọn codec phù hợp; đo riêng thời gian encode/decode với payload lớn.
- Cache kết quả tính toán phù hợp và có chính sách invalidation rõ ràng.
- Dùng thuật toán có độ phức tạp thấp hơn nếu profile cho thấy hotspot.
- Giới hạn concurrency của tác vụ CPU-heavy để tránh oversubscription.
- Đưa tác vụ tính toán dài ra khỏi event loop và dùng scheduler có giới hạn.

Với tác vụ CPU-bound, có thể dùng scheduler dành cho xử lý song song:

~~~java
import reactor.core.scheduler.Schedulers;

Mono<Report> buildReport(ReportRequest request) {
    return Mono.fromCallable(() -> cpuHeavyReportBuilder.build(request))
        .subscribeOn(Schedulers.parallel());
}
~~~

Đây là ví dụ khi `build()` thực sự là phép tính CPU-bound và chạy đồng bộ. Nếu tác vụ là I/O blocking, `Schedulers.parallel()` không phải lựa chọn phù hợp.

## Điểm nghẽn GC và bộ nhớ

### GC ảnh hưởng tới latency như thế nào?

Java tạo object cho payload, DTO, collection, buffer wrapper và các bước xử lý nghiệp vụ. Khi tốc độ allocation cao, GC phải làm việc thường xuyên hơn. Một số pha GC hoặc safepoint có thể tạm dừng application threads; pause dài thường xuất hiện thành spike latency.

Dấu hiệu cần chú ý:

- p99 tăng trùng thời điểm GC pause hoặc safepoint.
- GC time tăng so với thời gian chạy ứng dụng.
- Allocation rate cao, nhiều object sống ngắn.
- Heap sau GC vẫn tăng qua nhiều chu kỳ.
- Old generation tăng liên tục hoặc xuất hiện Full GC.
- CPU tăng ở các thread GC trong khi throughput giảm.

Heap sử dụng cao một mình chưa đủ để kết luận GC là bottleneck. Một heap lớn có thể được sử dụng ổn định với pause ngắn. Hãy xem pause duration, tần suất, allocation rate và xu hướng heap sau GC.

### Bật GC và safepoint log

Với JDK hiện đại, dùng Unified JVM Logging:

~~~bash
-Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags
~~~

Log giúp xem loại GC, thời gian pause, nguyên nhân collection, dung lượng heap trước/sau và thời gian ở safepoint. Cú pháp tag và level có thể điều chỉnh theo nhu cầu; tránh bật trace quá chi tiết liên tục nếu chưa cần.

Có thể xem thêm metric JVM do Spring Boot Actuator/Micrometer cung cấp:

- Heap và non-heap usage.
- Buffer pool, bao gồm direct buffer nếu runtime hỗ trợ.
- GC count và GC time.
- Thread count.
- CPU và process metrics.

### Phân biệt heap với direct memory

Reactor Netty/Netty thường dùng pooled byte buffers và direct memory cho I/O. Vì vậy:

- Heap thấp không có nghĩa tổng memory thấp.
- Direct memory tăng không nhất thiết là GC heap pause.
- Buffer bị giữ quá lâu có thể làm direct memory tăng.
- Payload lớn hoặc buffer leak có thể gây áp lực ngoài heap.

Theo dõi cả heap, direct memory và allocator metrics. Nếu nghi ngờ leak buffer, dùng leak detection hoặc công cụ profiling theo hướng dẫn của Netty trong môi trường kiểm thử trước khi bật chế độ tốn chi phí ở production.

### Hướng xử lý

- Giảm allocation không cần thiết trong đường xử lý nóng.
- Tránh tạo nhiều bản sao payload lớn.
- Dùng streaming/backpressure thay vì gom dữ liệu lớn vào collection.
- Kiểm tra object sống lâu, cache không giới hạn và buffer không được giải phóng.
- Chọn heap size và GC collector sau khi có dữ liệu pause, throughput và memory footprint.
- Không tăng heap một cách tự động: heap lớn hơn có thể làm tăng thời gian collection hoặc che khuất memory leak.

GC tuning là bước sau khi đã biết allocation và pause là nguyên nhân chính. Trước hết hãy giảm allocation và xác định object nào thực sự cần tồn tại.

## Điểm nghẽn event loop

### Event loop làm gì?

Reactor Netty dùng event loop để xử lý I/O và callback ngắn. Một nhóm event loop có thể phục vụ nhiều connection; thread không nên bị giữ lâu bởi blocking I/O hoặc phép tính nặng.

Reactor Netty mặc định dùng Event Loop Group chia sẻ giữa các server và client trong cùng JVM. Số worker thread mặc định dựa trên số processor runtime nhìn thấy, với mức tối thiểu được quy định bởi implementation. Vì tài nguyên được chia sẻ, một đoạn code blocking trên event loop có thể ảnh hưởng nhiều connection và nhiều stream.

### Dấu hiệu event loop bị nghẽn

- Nhiều connection cùng tăng latency trong cùng thời điểm.
- Event-loop pending tasks tăng.
- Callback và response bị trễ dù CPU không nhất thiết đạt 100%.
- Thread dump cho thấy event-loop thread đang chờ JDBC, file I/O, monitor lock hoặc lời gọi blocking.
- Một handler gọi `block()`, `Thread.sleep()`, `Future.get()` hoặc API đồng bộ trên thread xử lý I/O.
- Stream có consumer chậm hoặc callback làm quá nhiều công việc trên event loop.

Reactor Netty có metric:

```text
reactor.netty.eventloop.pending.tasks
```

Metric này là gauge số task đang chờ xử lý trên event loop. Khi dùng Reactor Netty builder trực tiếp, bật Micrometer integration bằng `.metrics(true)` và cấu hình registry phù hợp. Với Spring Boot auto-configured transport, kiểm tra instrumentation của đúng phiên bản thay vì giả định metric đã tự xuất hiện.

### Kiểm tra thread dump

Có thể lấy thread dump từ JVM đang chạy:

~~~bash
jcmd <pid> Thread.print
~~~

Nên thu thập vài thread dump cách nhau một khoảng ngắn trong lúc lỗi đang xảy ra. Một stack trace đơn lẻ chỉ là ảnh chụp tại một thời điểm; cùng một event-loop thread liên tục nằm trong JDBC driver, file I/O hoặc lock qua nhiều lần dump là bằng chứng mạnh hơn.

Tìm các thread có tên liên quan tới Reactor Netty/Netty event loop, ví dụ tên chứa `reactor-tcp-nio`, `reactor-http-nio` hoặc `nioEventLoop` tùy phiên bản và cấu hình.

Nếu stack trace của event-loop thread nằm trong JDBC driver, file I/O, `block()`, lock contention hoặc một method tính toán lâu, đó là bằng chứng mạnh cho thấy event loop đang bị giữ. Một thread ở trạng thái RUNNABLE chưa chắc là CPU hotspot; hãy đối chiếu JFR và CPU profile.

### Offload blocking I/O đúng cách

Nếu phải gọi API blocking, bọc lời gọi bằng `Mono.fromCallable` và chuyển subscription sang bounded elastic scheduler:

~~~java
import reactor.core.scheduler.Schedulers;

Mono<Customer> loadCustomer(String id) {
    return Mono.fromCallable(() -> blockingCustomerRepository.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Đặt scheduler tại nguồn blocking. Không gọi blocking method trước khi tạo publisher:

~~~java
// Sai: lời gọi blocking xảy ra ngay khi method được gọi.
Mono<Customer> wrong(String id) {
    Customer customer = blockingCustomerRepository.findById(id);
    return Mono.just(customer);
}
~~~

Nếu thư viện có API reactive/non-blocking, ưu tiên dùng API đó. Bounded elastic có giới hạn tài nguyên; không biến nó thành nơi chạy mọi công việc và không tạo scheduler mới cho từng request.

Trong môi trường phát triển/kiểm thử, có thể cân nhắc BlockHound để phát hiện một số lời gọi blocking trên thread được đánh dấu non-blocking. Đây là công cụ hỗ trợ phát hiện sớm; nó không thay thế thread dump và kiểm thử tải trên transport thật.

Với CPU-heavy work, dùng scheduler CPU-bound như `Schedulers.parallel()` hoặc một scheduler riêng có giới hạn. Không dùng bounded elastic như giải pháp mặc định cho phép tính CPU.

### Không tăng event loop trước khi tìm nguyên nhân

Tăng số event loop có thể giúp khi số worker hiện tại thực sự không đáp ứng tải I/O, nhưng cũng làm tăng context switching và cạnh tranh CPU. Nếu nguyên nhân là blocking call, thêm event loop chỉ tạo thêm thread có thể bị block.

Trước khi tùy chỉnh `LoopResources`, hãy xác minh pending tasks, thread dump, CPU, connection count và số core được cấp cho process. Khi dùng custom resources, phải quản lý dispose theo vòng đời ứng dụng và tránh vô tình tạo nhiều group không cần thiết.

## Điểm nghẽn ở dịch vụ phụ thuộc

Một handler RSocket có thể chỉ mất vài mili giây để xử lý, nhưng phải chờ database, cache, HTTP service, RSocket service khác hoặc message broker.

### Dấu hiệu

- CPU và event loop của service hiện tại tương đối bình thường.
- Server handler latency tăng cùng downstream latency.
- Distributed trace có một span dependency chiếm phần lớn thời gian.
- Connection pool có nhiều request chờ acquire.
- Retry tăng, timeout tăng hoặc circuit breaker thường xuyên mở.
- Queue depth và consumer lag tăng.
- Một dependency cụ thể chậm hơn các dependency còn lại.

### Tách thời gian từng dependency

Đo riêng:

- Thời gian chờ connection pool.
- Thời gian connect/TLS nếu tạo connection mới.
- Thời gian request tới dependency và nhận response.
- Thời gian query database.
- Thời gian retry và backoff.
- Thời gian xử lý sau khi nhận kết quả.

Không gộp thời gian chờ connection pool vào thời gian server xử lý remote request mà không ghi rõ. Nếu connection pool cạn, request có thể chưa hề được gửi đi.

### Ví dụ đo outbound RSocket call

Đo latency ở ranh giới gọi service từ xa:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

class PricingClient {

    private final RSocketRequester requester;
    private final MeterRegistry registry;

    PricingClient(
            RSocketRequester requester,
            MeterRegistry registry) {
        this.requester = requester;
        this.registry = registry;
    }

    Mono<Quote> quote(QuoteRequest request) {
        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(registry);

            return requester
                .route("pricing.quote")
                .data(request)
                .retrieveMono(Quote.class)
                .doFinally(signal -> {
                    String outcome =
                        signal == SignalType.ON_COMPLETE ? "completed" :
                        signal == SignalType.ON_ERROR ? "error" :
                        signal == SignalType.CANCEL ? "cancelled" : "other";

                    sample.stop(
                        Timer.builder("rsocket.dependency.duration")
                            .tag("dependency", "pricing")
                            .tag("outcome", outcome)
                            .register(registry)
                    );
                });
        });
    }
}
~~~

Timer đo thời gian từ lúc publisher được subscribe tới terminal signal. Nó bao gồm thời gian chờ response trên RSocket call, nhưng không tự tách riêng network, remote handler và remote dependency. Muốn tách các chặng, cần trace ở cả hai service hoặc thêm instrumentation ở server handler.

Không đặt URL động, user ID, request ID hoặc exception message vào metric tag. Dùng trace/span để tra cứu từng request cụ thể.

### Hướng xử lý

- Tối ưu query và index nếu database là bottleneck.
- Điều chỉnh pool size theo capacity thực tế của dependency, không tăng vô hạn.
- Dùng timeout theo SLA và deadline tổng thể của request.
- Retry có giới hạn, backoff và jitter; không retry lỗi không thể phục hồi.
- Dùng circuit breaker/bulkhead để cô lập dependency chậm.
- Cache dữ liệu phù hợp và đặt TTL/invalidation rõ ràng.
- Giới hạn concurrency và queue để tránh tạo backlog vô hạn.
- Trả trạng thái bất đồng bộ/job ID khi nghiệp vụ quá dài thay vì giữ request mở không giới hạn.

Retry có thể khuếch đại sự cố. Nếu dependency đã quá tải, nhiều caller retry đồng thời có thể làm tải tăng thêm. Theo dõi retry rate cùng dependency latency và error rate.

## Metric và công cụ nên kết hợp

Spring Boot Actuator/Micrometer có thể cung cấp các metric nền tảng của JVM và process, như CPU, GC, heap, thread và buffer pool. Reactor Netty cung cấp metric transport khi instrumentation được bật và tích hợp đúng registry.

| Nhóm | Metric/bằng chứng | Công cụ |
|---|---|---|
| Network | RTT, retransmit, reset, bytes, socket queue | `ss`, `netstat`, packet capture, network telemetry |
| CPU | Process/container CPU, execution samples, runnable threads | JFR, profiler, container metrics |
| GC | Pause duration, GC count/time, allocation, heap after GC | GC log, JFR, Actuator |
| Event loop | Pending tasks, thread stack, callback delay | Reactor Netty metrics, `jcmd Thread.print`, JFR |
| Dependency | Client span, pool wait, query time, retries | Distributed tracing, dependency metrics |
| Memory ngoài heap | Direct buffer usage, allocator metrics | Micrometer, Reactor Netty/Netty metrics |

Một số metric Reactor Netty hữu ích tùy transport/version:

- `reactor.netty.eventloop.pending.tasks`: số task đang chờ event loop.
- `reactor.netty.bytebuf.allocator.active.direct.memory`: direct memory đang được allocator sử dụng ở các phiên bản có metric này.
- Metric connection provider/pending acquire: thời gian hoặc số yêu cầu đang chờ lấy connection khi có connection pool.

Tên và sự hiện diện của meter phụ thuộc phiên bản Reactor Netty và transport. Kiểm tra danh sách meter thực tế qua registry thay vì copy tên từ tài liệu của phiên bản khác.

Ví dụ bật metrics cho TCP client/server Reactor Netty trực tiếp:

~~~java
import reactor.netty.tcp.TcpClient;
import reactor.netty.tcp.TcpServer;

TcpClient client = TcpClient.create()
    .host("inventory-service")
    .port(7000)
    .metrics(true);

TcpServer server = TcpServer.create()
    .metrics(true);
~~~

Ví dụ minh họa API Reactor Netty trực tiếp. Trong ứng dụng Spring Boot dùng RSocket auto-configuration, không thay transport hoặc tạo server/client riêng chỉ để bật metric. Hãy kiểm tra cách phiên bản Spring Boot/RSocket đang dùng cấu hình Reactor Netty và Micrometer.

## Quy trình chẩn đoán theo thứ tự

Dùng cùng một request ID trong log/trace để so sánh thời gian client, server handler và dependency.

~~~mermaid
flowchart TD
    A[Latency tăng] --> B{Server handler cũng chậm?}
    B -->|Không| C[Kiểm tra network, proxy, client, serialization]
    B -->|Có| D{CPU process/container cao?}
    D -->|Có| E[JFR CPU profile, kiểm tra GC và throttling]
    D -->|Không| F{GC pause trùng spike?}
    F -->|Có| G[Đọc GC log, allocation và heap sau GC]
    F -->|Không| H{Event loop pending hoặc thread bị block?}
    H -->|Có| I[Thread dump, tìm blocking call và lock]
    H -->|Không| J{Downstream span chậm?}
    J -->|Có| K[Đo pool, query, remote latency và retry]
    J -->|Không| L[Kiểm tra queue, codec, lock và các ranh giới chưa instrument]
~~~

Thực hiện theo trình tự:

1. Xác nhận triệu chứng bằng p95/p99, throughput, error rate và active streams.
2. So sánh client end-to-end latency với server handler latency.
3. Nếu server handler thấp, kiểm tra network, proxy, client và encode/decode.
4. Nếu handler cao, kiểm tra CPU, GC và event loop.
5. Đọc trace để xác định dependency nào chiếm thời gian.
6. Thu JFR, GC log hoặc thread dump trong cửa sổ có vấn đề.
7. Đưa ra một giả thuyết có thể kiểm chứng.
8. Thay đổi một yếu tố, chạy lại cùng kịch bản tải và so sánh.
9. Theo dõi error, memory, throughput và saturation sau thay đổi để chắc rằng bottleneck không chỉ chuyển sang nơi khác.

## Tình huống thực tế: request p99 tăng từ 80 ms lên 900 ms

Giả sử dashboard cho thấy p99 request-response tăng lên 900 ms. Đừng vội tăng connection hoặc event-loop threads.

| Bằng chứng quan sát | Kết luận tạm thời | Bước tiếp theo |
|---|---|---|
| Client p99 900 ms, server handler p99 40 ms | Phần chậm nằm ngoài handler | Kiểm tra RTT, proxy, serialization và client |
| Server handler p99 900 ms, CPU 95%, JFR cho thấy JSON mapping chiếm nhiều sample | CPU hotspot | Tối ưu codec/mapping và đo lại |
| p99 tăng đúng lúc GC pause 700 ms | GC/safepoint có liên quan | Kiểm tra allocation và heap sau GC |
| CPU 35%, event-loop pending tasks tăng, thread dump có JDBC call trên event loop | Event loop bị blocking | Offload blocking I/O hoặc chuyển sang driver reactive |
| Handler span 850 ms, database span 820 ms | Database là dependency bottleneck | Kiểm tra query plan, lock, pool và index |
| Database span thấp nhưng chờ acquire connection 500 ms | Connection pool bị bão hòa | Kiểm tra pool size, connection leak và concurrency |

Đây là các giả thuyết chẩn đoán. Cần xác minh bằng trace, profile và số đo cùng thời điểm trước khi thay đổi cấu hình.

## Những cách xử lý dễ làm tình hình tệ hơn

- **Tăng event loop để chữa blocking:** event loop mới vẫn có thể bị block và làm CPU/context switching tăng.
- **Tăng heap để chữa mọi latency spike:** nếu nguyên nhân là allocation churn hoặc leak, vấn đề chỉ bị trì hoãn.
- **Tăng connection pool vô hạn:** có thể làm database nhận nhiều truy vấn đồng thời hơn khả năng phục vụ.
- **Retry ngay lập tức:** khuếch đại tải khi dependency đang quá tải.
- **Gom stream thành List:** tăng heap và allocation, làm mất lợi ích backpressure.
- **Đưa blocking I/O vào `map`:** callback có thể chạy trên event-loop thread.
- **Đo trung bình thay p95/p99:** che khuất nhóm request chậm.
- **Đổi nhiều tham số cùng lúc:** không biết thay đổi nào tạo ra kết quả.

## Checklist trước khi kết luận bottleneck

1. Đã phân biệt client end-to-end latency với server handler latency chưa?
2. Đã đo request rate, payload size và throughput cùng thời điểm chưa?
3. RTT, retransmission và network queue có bất thường không?
4. CPU process/container có bị saturation hoặc throttling không?
5. JFR có chỉ ra method CPU-heavy hoặc allocation hotspot không?
6. GC pause và safepoint có trùng thời điểm latency spike không?
7. Heap sau GC và direct memory có xu hướng bất thường không?
8. Event-loop pending tasks có tăng không?
9. Thread dump có blocking call hoặc lock contention trên event loop không?
10. Dependency span, pool wait, query latency và retry rate có tăng không?
11. Đã kiểm tra queue/backpressure và active stream chưa?
12. Sau khi sửa, đã chạy lại đúng kịch bản tải và kiểm tra bottleneck mới chưa?

Một request RSocket chậm không đồng nghĩa mạng chậm. Hãy tách đường đi thành các chặng và đối chiếu latency với CPU, GC, event loop và dependency. Dùng JFR để tìm hotspot, GC log để xác minh pause, thread dump và event-loop metrics để tìm blocking, còn trace để xác định dependency. Chỉ tối ưu sau khi bằng chứng chỉ ra một nguyên nhân cụ thể; sau đó chạy lại cùng tải để xác nhận latency cải thiện mà không chuyển áp lực sang thành phần khác.

## Tài liệu tham khảo

- [Spring Boot Reference: Metrics and Micrometer](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Reactor Netty Reference Guide: TCP, event loop and metrics](https://docs.spring.io/projectreactor/reactor-netty/docs/current/reference/html/index.html)
- [Reactor Netty: Event Loop Group](https://docs.spring.io/projectreactor/reactor-netty/docs/current/reference/html/index.html)
- [Oracle JDK 21: jcmd diagnostic commands](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21: Unified JVM Logging](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Oracle JDK 21: jfr command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle Java Flight Recorder and Java Mission Control](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
- [Micrometer Reference: JVM metrics and instrumentation](https://docs.micrometer.io/micrometer/reference/)
- [Project Reactor BlockHound](https://github.com/reactor/BlockHound)

