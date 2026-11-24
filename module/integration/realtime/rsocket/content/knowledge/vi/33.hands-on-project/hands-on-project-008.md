# Đo tải, tìm điểm nghẽn và kiểm tra giới hạn bộ nhớ

Một ứng dụng RSocket có thể xử lý nhiều interaction đồng thời trên một kết nối TCP hoặc WebSocket. Vì vậy, phép đo hiệu năng phải xem xét cả thông lượng request, độ trễ từng interaction, số kết nối, mức tiêu thụ tài nguyên và cách hệ thống phản ứng khi consumer hoặc dependency xử lý chậm. Chỉ đo số request/giây trong một bài thử ngắn chưa đủ để kết luận hệ thống có thể vận hành ổn định.

Bài thực hành này xây dựng một quy trình đo có thể lặp lại cho client/server Java và Spring Boot. Bạn sẽ tạo tải bằng RSocket client thật, thay đổi concurrency và payload, quan sát CPU, event loop, GC, heap và direct memory, sau đó tìm giới hạn an toàn bằng cách tăng tải có kiểm soát. Các kết quả cần được so sánh trên cùng transport, cấu hình JVM, dữ liệu và môi trường.

~~~mermaid
flowchart TD
    A["Xác định workload và SLO"] --> B["Tạo baseline"]
    B --> C["Tăng tải theo từng bậc"]
    C --> D["Thu metrics và profile"]
    D --> E{"Có dấu hiệu bão hòa?"}
    E -->|Chưa| C
    E -->|Có| F["Khoanh vùng CPU, I/O, event loop, GC, memory"]
    F --> G["Điều chỉnh một yếu tố"]
    G --> H["Chạy lại cùng kịch bản"]
    H --> I["Ghi nhận capacity và giới hạn"]
~~~

## 1. Xác định mục tiêu và workload trước khi đo

Trước khi chạy benchmark, mô tả tải gần với hành vi production. Cần biết client dùng TCP hay WebSocket, loại interaction nào chiếm ưu thế, kích thước payload ở mỗi chiều, số kết nối đồng thời, thời lượng phiên, tần suất message và dependency mà handler gọi tới.

| Thành phần workload | Ví dụ cần xác định |
|---|---|
| Transport | RSocket TCP, RSocket qua WebSocket, có TLS hay không |
| Interaction | request-response, fire-and-forget, request-stream, request-channel |
| Payload | 64 B, 1 KB, 16 KB, 64 KB; định dạng JSON, CBOR hoặc codec thực tế |
| Kết nối | 1, 10, 100 hoặc số kết nối mục tiêu; số client process |
| Concurrency | Số interaction đang chờ phản hồi trên mỗi client |
| Tốc độ phát sinh | Closed-loop theo concurrency hoặc open-loop theo arrival rate |
| Dependency | Handler thuần CPU, cache, database, HTTP service hoặc message broker |
| Thời lượng | Warm-up, thời gian đo ổn định, thời gian nghỉ giữa các lượt |

Chọn SLO để đánh giá kết quả, ví dụ p95 và p99 latency tối đa, tỷ lệ lỗi tối đa và mức thông lượng thành công cần đạt. Các con số phải lấy từ yêu cầu của hệ thống; không dùng một ngưỡng chung cho mọi ứng dụng. Ghi lại phiên bản JDK, Spring Boot, RSocket, Reactor, Netty, số CPU, giới hạn container, JVM flags và cấu hình proxy để có thể tái lập phép đo.

Phân biệt hai cách tạo tải:

- **Closed-loop:** mỗi worker chỉ gửi interaction tiếp theo sau khi interaction hiện tại hoàn tất. Cách này dễ kiểm soát số request đang chạy và phù hợp để đo mức thông lượng theo concurrency. Khi server chậm, tốc độ phát sinh tự giảm theo phản hồi; vì vậy nó có thể che khuất hàng đợi và độ trễ của một arrival rate cố định.
- **Open-loop:** phát sinh interaction theo lịch độc lập với thời gian phản hồi. Cách này giúp kiểm tra hệ thống khi tốc độ đến không giảm theo độ trễ, nhưng cần giới hạn số interaction đang chờ và ghi nhận request bị bỏ hoặc bị từ chối. Nếu không, chính load generator có thể tích tụ bộ nhớ.

Không so sánh kết quả closed-loop với open-loop như thể chúng là cùng một workload. Nếu cần tìm giới hạn khi tải tăng, hãy chạy cả hai kiểu và ghi rõ cách phát sinh request.

## 2. Thiết lập phép đo có thể lặp lại

Một vòng đo cơ bản nên gồm:

1. Khởi động server và dependency; chờ health check sẵn sàng.
2. Tạo kết nối RSocket và hoàn tất Setup trước khi bắt đầu tính latency của business interaction.
3. Chạy warm-up để JIT, cache, connection pool và allocator đạt trạng thái ổn định.
4. Chạy một mức tải cố định đủ lâu để quan sát xu hướng, không chỉ lấy một mẫu tức thời.
5. Ghi throughput thành công, p50/p95/p99, lỗi, timeout, reconnect và metrics tài nguyên.
6. Đợi hệ thống trở về trạng thái nền trước khi chạy mức tiếp theo.
7. Lặp lại mỗi cấu hình ít nhất vài lần và so sánh median cùng độ dao động.

Ví dụ ma trận thí nghiệm ban đầu:

| Lượt | Kết nối client | Concurrency mỗi kết nối | Payload | Mục tiêu |
|---|---:|---:|---:|---|
| A | 1 | 1 | 1 KB | Baseline latency |
| B | 1 | 32 | 1 KB | Multiplex nhiều interaction trên một kết nối |
| C | 1 | 128 | 1 KB | Tìm điểm bão hòa concurrency |
| D | 10 | 32 | 1 KB | Tăng số kết nối vật lý |
| E | 10 | 32 | 16 KB | Đo ảnh hưởng payload và serialization |
| F | 10 | 32 | 64 KB | Quan sát throughput mạng và memory |
| G | 10 | 32 | 1 KB | Mô phỏng consumer chậm hoặc dependency chậm |

Đây là ma trận khởi đầu, không phải cấu hình production khuyến nghị. Sau baseline, chỉ thay đổi một biến trong mỗi lượt để xác định nguyên nhân. Khi so sánh TCP với WebSocket, giữ nguyên payload, concurrency, số kết nối, TLS, handler và vị trí máy chạy benchmark.

Load generator phải có đủ CPU, network bandwidth và memory để không trở thành bottleneck. Nếu CPU của máy phát tải đã bão hòa, kết quả không phản ánh capacity của server. Khi cần tải lớn, chạy nhiều client process hoặc máy phát tải độc lập và cộng kết quả từ các client.

## 3. Tạo tải bằng RSocket client thật

Không dùng benchmark HTTP thông thường để đại diện cho RSocket. HTTP load tool không thực hiện RSocket Setup, REQUEST_N, CANCEL hay multiplex các interaction trên cùng một phiên RSocket. Dùng một client RSocket thật và gọi đúng route, codec, metadata, xác thực và transport của ứng dụng.

Ví dụ dưới đây giả định requester đã kết nối tới server trước khi đo, registry là Micrometer MeterRegistry, và route bench.echo trả về một phản hồi nhỏ. Mẫu dùng một RSocket session để đo multiplexing; hãy chạy thêm các lượt với nhiều session độc lập để đánh giá phân phối tải ở cấp kết nối.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;

record BenchRequest(long id, byte[] payload) {}
record BenchReply(long id, int payloadBytes) {}

public final class RSocketLoadScenario {

    public static void run(
            RSocketRequester requester,
            MeterRegistry registry,
            int totalRequests,
            int concurrency,
            int payloadBytes) {

        byte[] payload = new byte[payloadBytes];
        AtomicLong completed = new AtomicLong();
        AtomicLong failed = new AtomicLong();

        Timer latency = Timer.builder("rsocket.bench.latency")
                .publishPercentileHistogram()
                .register(registry);

        long startedAt = System.nanoTime();

        Flux.range(0, totalRequests)
                .flatMap(id -> Mono.defer(() -> {
                    Timer.Sample sample = Timer.start(registry);

                    return requester.route("bench.echo")
                            .data(new BenchRequest(id, payload))
                            .retrieveMono(BenchReply.class)
                            .doOnNext(reply -> completed.incrementAndGet())
                            .doOnError(error -> failed.incrementAndGet())
                            .doFinally(signal -> sample.stop(latency))
                            .onErrorResume(error -> Mono.empty());
                }), concurrency)
                .then()
                .block(Duration.ofMinutes(10));

        double elapsedSeconds =
                (System.nanoTime() - startedAt) / 1_000_000_000.0;

        System.out.printf(
                "completed=%d failed=%d elapsed=%.2fs throughput=%.1f req/s%n",
                completed.get(),
                failed.get(),
                elapsedSeconds,
                completed.get() / elapsedSeconds);
    }
}
~~~

Server handler tối giản tương ứng:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class BenchmarkHandler {

    @MessageMapping("bench.echo")
    Mono<BenchReply> echo(BenchRequest request) {
        return Mono.just(
                new BenchReply(request.id(), request.payload().length));
    }
}
~~~

Đoạn handler trên chỉ tạo baseline cho đường đi request-response và codec. Nó chưa đại diện cho một nghiệp vụ có database hoặc CPU nặng. Hãy tạo scenario riêng cho từng route thực tế và bật đúng metadata, authentication, TLS, proxy cùng codec đang dùng ở production. Đối với request-stream, tiêu thụ toàn bộ Flux trong benchmark và đếm phần tử; tránh collectList() với stream lớn vì nó giữ toàn bộ kết quả trong heap. Với request-channel, đo riêng cả chiều client gửi lên và chiều server trả về, đồng thời kiểm tra demand/backpressure ở hai chiều.

Concurrency trong ví dụ là số interaction đồng thời trên một kết nối. Nó không phải số TCP socket. Tăng concurrency từ 32 lên 128 có thể làm tăng số request đang chờ mà không tạo thêm kết nối vật lý. Tạo thêm nhiều RSocketRequester session trong một scenario riêng để đo ảnh hưởng của connection count, handshake, phân phối load balancer và trạng thái phiên.

Micrometer Timer có thể cung cấp histogram để tính p50/p95/p99 ở backend metrics. Cấu hình retention và bucket phù hợp với latency SLO của hệ thống. Không chỉ in trung bình: trung bình thấp vẫn có thể che khuất một tail latency rất cao. Với benchmark độc lập, có thể dùng HDR Histogram hoặc công cụ tương đương để lưu phân phối latency chi tiết.

## 4. Đọc throughput, latency và lỗi đúng cách

Các chỉ số cần được ghi đồng thời:

| Chỉ số | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| Offered rate | Số interaction client cố phát sinh mỗi giây | Thấp hơn cấu hình có thể do load generator bão hòa |
| Completed throughput | Số interaction thành công mỗi giây | Không tăng dù tăng tải có thể hệ thống đã bão hòa |
| p50 / p95 / p99 latency | Thời gian hoàn tất interaction | p99 tăng mạnh trước khi throughput giảm thường báo hiệu queue hoặc contention |
| Error / timeout rate | Interaction thất bại hoặc hết hạn | Tăng cùng concurrency có thể chỉ ra giới hạn tài nguyên hoặc dependency |
| In-flight interactions | Số interaction đã gửi nhưng chưa hoàn tất | Tăng liên tục cho thấy tốc độ đến vượt khả năng xử lý |
| Connection count / reconnect | Phiên vật lý đang mở và số lần kết nối lại | Reconnect tăng có thể làm phát sinh thêm handshake storm |
| Payload throughput | Byte/giây hai chiều | Giúp phân biệt giới hạn CPU với network bandwidth |

Luôn báo cáo cả offered rate và completed throughput. Nếu client chỉ gửi request tiếp theo sau khi nhận response, tốc độ gửi có thể giảm khi server chậm và không thể hiện lượng tải mà hệ thống phải chịu trong một kịch bản open-loop. Ghi nhận request bị từ chối, bị drop và số interaction đang chờ; không loại chúng khỏi báo cáo.

Một kết quả có thể được xem là mức tải bền vững khi throughput hoàn tất ổn định, p95/p99 nằm trong SLO, lỗi nằm trong giới hạn, in-flight và queue không tăng không kiểm soát, đồng thời heap/direct memory và GC không có xu hướng tăng liên tục. Ghi rõ điều kiện này cùng cấu hình thử nghiệm để người khác có thể lặp lại.

## 5. Tìm điểm nghẽn theo từng lớp

Khi throughput không tăng hoặc latency tăng nhanh, khoanh vùng theo thứ tự từ client tới server và dependency. Không thay đồng thời thread pool, heap, concurrency và payload vì khi kết quả thay đổi sẽ khó biết yếu tố nào có tác động.

### 5.1. Kiểm tra load generator và mạng

Đo CPU, heap, network và số socket ở máy phát tải. Kiểm tra liệu client có đang serialize payload quá tốn CPU, ghi log từng request, hoặc dùng một event loop không đủ năng lực hay không. Chạy client trên máy khác server để tránh hai tiến trình tranh chấp CPU và memory. So sánh số byte gửi/nhận với kích thước payload dự kiến, bao gồm overhead của codec, framing, TLS và WebSocket.

Nếu một RSocket connection đạt giới hạn nhưng server còn dư tài nguyên, chạy nhiều session độc lập. RSocket multiplex các interaction trên một kết nối, nhưng một kết nối đơn không nhất thiết tận dụng hết CPU hoặc network của nhiều node. Khi có load balancer, backend thường được chọn lúc mở kết nối; tăng số interaction trên một session không làm các interaction đó tự chuyển sang node khác.

### 5.2. Kiểm tra CPU và serialization

CPU cao cùng throughput gần như không tăng là dấu hiệu cần profile. Dùng Java Flight Recorder (JFR) hoặc async-profiler để xem thời gian nằm ở serialization, mã nghiệp vụ, mã hóa TLS, nén, logging hay thư viện bên ngoài. So sánh handler rỗng với handler thực tế để ước lượng chi phí của transport và codec.

Kiểm tra payload lớn có tạo bản sao byte array hoặc object trung gian không. JSON có thể tạo allocation đáng kể và biểu diễn byte array khác với codec nhị phân. Benchmark phải dùng codec thực tế; nếu đổi codec, đó là một thí nghiệm riêng.

### 5.3. Kiểm tra Reactor và Netty event loop

Netty event loop phục vụ nhiều channel. Một tác vụ blocking hoặc xử lý CPU lâu trên event loop có thể làm chậm nhiều kết nối cùng lúc. Dấu hiệu gồm latency tăng trên nhiều route, event loop thread bận, pending task tăng và thread dump cho thấy event loop đang chờ JDBC, HTTP blocking, file I/O hoặc lock.

Không gọi block(), thao tác JDBC blocking hoặc chờ lock dài trong handler chạy trên event loop. Nếu cần gọi API blocking, chuyển phần việc đó sang scheduler phù hợp và giới hạn số tác vụ đồng thời để không tạo một hàng đợi vô hạn. Với I/O reactive, kiểm tra connection pool và thời gian chờ dependency thay vì tăng số event loop một cách tùy tiện.

### 5.4. Kiểm tra dependency và pool

Nếu handler gọi database, HTTP service hoặc broker, đo riêng thời gian chờ dependency, active/pending connection, timeout và retry. Một pool nhỏ có thể tạo queue dù CPU của ứng dụng còn thấp; tăng pool quá lớn lại có thể làm database hoặc downstream quá tải. Tách benchmark handler thuần khỏi benchmark end-to-end để xác định phần thời gian nằm ở đâu.

### 5.5. Kiểm tra backpressure và hàng đợi

Theo dõi số phần tử đang chờ, in-flight interactions, queue của scheduler và tốc độ consumer. Với request-stream/request-channel, xác minh publisher tôn trọng demand và consumer không bị ép nhận dữ liệu nhanh hơn khả năng xử lý. Kiểm tra hành vi khi client gửi CANCEL hoặc disconnect giữa stream.

Các thao tác như collectList(), cache() trên luồng lớn, flatMap với concurrency không giới hạn hoặc onBackpressureBuffer() không đặt dung lượng có thể làm bộ nhớ tăng theo thời gian. Dùng concurrency hữu hạn, buffer có giới hạn và chính sách overflow rõ ràng như từ chối, drop có kiểm soát hoặc báo lỗi theo yêu cầu nghiệp vụ. limitRate điều chỉnh cách yêu cầu dữ liệu upstream; nó không thay thế việc đặt giới hạn cho mọi queue trong ứng dụng.

## 6. Đo heap, direct memory và native memory

Không đồng nhất bộ nhớ JVM heap với toàn bộ memory process. RSocket trên Netty có thể dùng heap object, direct buffer, thread stack, metaspace, code cache và các vùng native khác. Trong container, RSS/cgroup memory còn bao gồm nhiều thành phần mà biểu đồ heap không thể hiện.

| Vùng bộ nhớ | Thành phần thường gặp | Công cụ quan sát |
|---|---|---|
| Java heap | DTO, object Reactor, collection, queue, payload được copy | JFR, GC logs, jcmd GC.heap_info, heap histogram |
| Direct/NIO buffer | ByteBuffer ngoài heap, buffer I/O | Micrometer jvm.buffer.memory.used, buffer pool MXBean |
| Netty pooled buffer | Arena, chunk, direct/heap ByteBuf được tái sử dụng | Netty allocator metrics nếu ứng dụng expose; RSS và direct memory |
| Metaspace / code cache | Class metadata và mã JIT | Native Memory Tracking, JVM memory metrics |
| Thread stack | Stack của event loop, worker và thread khác | Thread count, NMT, RSS |
| Native/other | TLS, allocator, JNI, thư viện native và mapping | NMT kết hợp OS/container metrics |

jvm.buffer.memory.used hữu ích để theo dõi NIO buffer pool nhưng không đại diện cho mọi vùng native hoặc mọi allocation nội bộ của Netty. Netty có thể quản lý direct buffer qua allocator riêng; hãy expose metrics của allocator đang dùng và kiểm chứng với RSS. Native Memory Tracking cũng không theo dõi đầy đủ mọi allocation của thư viện bên thứ ba hoặc mọi vùng off-heap.

Một cách đọc bộ nhớ hữu ích là so sánh ba mốc: trước khi warm-up, sau warm-up và sau khi chạy tải ổn định rồi để hệ thống idle. Heap có thể tăng trong lúc tải và giảm sau GC; điều cần chú ý là mức heap sau GC có tiếp tục tăng qua nhiều chu kỳ hay không. Direct memory có thể giữ lại trong pool để tái sử dụng nên không nhất thiết giảm ngay khi traffic giảm. Hãy phân biệt pool được giữ lại để tái sử dụng với allocation tăng không giới hạn.

### 6.1. Quan sát heap và GC

Khởi chạy ứng dụng với GC log để biết thời gian và tần suất thu gom:

~~~bash
java \
  -Xms2g -Xmx2g \
  -Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags \
  -jar rsocket-service.jar
~~~

Các giá trị heap trên chỉ là ví dụ cho môi trường benchmark có đủ RAM. Trong container, phải tính tổng heap, direct memory, metaspace, thread stack, code cache và overhead của native so với memory limit. Đặt Xmx bằng toàn bộ giới hạn container có thể khiến process bị OOMKilled dù heap chưa đạt Xmx.

Lệnh quan sát tiến trình đang chạy:

~~~bash
jcmd <pid> GC.heap_info
jcmd <pid> GC.class_histogram
jstat -gcutil <pid> 1000
~~~

GC.class_histogram có thể tốn thời gian và ảnh hưởng tiến trình khi heap lớn; chỉ chạy trong môi trường kiểm thử hoặc khi đã đánh giá tác động. Nếu cần heap dump, lưu đủ dung lượng đĩa và thực hiện theo quy trình vận hành vì thao tác này có thể gây pause đáng kể.

### 6.2. Quan sát direct và native memory

Bật Native Memory Tracking (NMT) từ lúc khởi động:

~~~bash
java \
  -Xms2g -Xmx2g \
  -XX:NativeMemoryTracking=summary \
  -XX:MaxDirectMemorySize=1g \
  -jar rsocket-service.jar
~~~

Các giới hạn trên chỉ là ví dụ minh họa. MaxDirectMemorySize kiểm soát một số cơ chế direct buffer của JVM; nó không phải giới hạn tổng native memory của process. Cách Netty cấp phát direct memory còn phụ thuộc phiên bản, allocator và cấu hình. Cần đối chiếu số liệu allocator, NMT và RSS thay vì xem một cờ JVM là hàng rào duy nhất.

Sau khi ứng dụng chạy, lấy baseline và so sánh:

~~~bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary scale=MB
jcmd <pid> VM.native_memory summary.diff scale=MB
~~~

NMT phải được bật khi JVM khởi động. Nó có overhead và không ghi nhận đầy đủ mọi allocation native từ thư viện bên ngoài JVM. Khi chạy trong container, theo dõi thêm RSS và memory usage của cgroup để biết tổng bộ nhớ mà process thực sự sử dụng.

Nếu dùng Netty PooledByteBufAllocator, expose các số liệu allocator tương ứng với phiên bản Netty đang dùng, chẳng hạn số arena, số allocation và lượng memory được cấp phát theo heap/direct. Không gọi allocator metrics trong từng message; lấy theo chu kỳ từ metrics exporter. Pooled memory có thể vẫn được giữ lại sau khi tải giảm để tái sử dụng, do đó cần quan sát xu hướng theo thời gian và mức sử dụng thực tế.

### 6.3. Kiểm tra rò rỉ ByteBuf/Payload

Nếu nghi ngờ quên release reference-counted buffer hoặc giữ Payload quá lâu, bật leak detection ở môi trường kiểm thử:

~~~bash
java -Dio.netty.leakDetection.level=advanced -jar rsocket-service.jar
~~~

Leak detector có overhead và có thể tạo log lớn. Chỉ bật trong một lượt chẩn đoán có kiểm soát; paranoid còn tốn chi phí hơn và không phù hợp làm cấu hình tải production. Khi có cảnh báo, lần theo nơi cấp phát và nơi ownership được chuyển giao hoặc release. Kiểm tra cả đường success, error, cancel và disconnect; đường hủy stream thường dễ bị bỏ sót.

## 7. Đo bằng JFR và đọc dấu vết

JFR giúp quan sát CPU sample, allocation, GC pause, thread park, monitor contention, socket I/O và nhiều sự kiện JVM khác. Trên JDK hỗ trợ JFR, có thể ghi một profile trong khoảng thời gian benchmark:

~~~bash
jcmd <pid> JFR.start name=rsocket-load settings=profile duration=180s filename=rsocket-load.jfr
~~~

Mở file rsocket-load.jfr bằng Java Mission Control để kiểm tra:

- Hot methods và CPU sample tập trung ở handler, serializer, codec hay TLS.
- Allocation theo class và call stack, đặc biệt byte array, buffer wrapper và collection.
- GC pause, allocation rate và thời gian dành cho garbage collection.
- Thread park, monitor contention và các event loop thread bị chặn.
- Socket read/write latency nếu sự kiện và cấu hình ghi nhận có sẵn.

Khi profile, giữ cùng một workload và thời lượng với lượt benchmark đối chứng. Profiling có overhead; không dùng kết quả khi profiler bật để thay thế số liệu benchmark không profiler. Lưu cả file JFR, cấu hình chạy và timestamp để liên hệ với dashboard.

## 8. Tìm giới hạn bộ nhớ và concurrency an toàn

Tăng tải theo từng bậc và quan sát điểm mà một trong các điều kiện SLO không còn đạt. Ví dụ, tăng concurrency 1 → 8 → 16 → 32 → 64 → 128, nhưng dừng hoặc giảm tải nếu lỗi, queue hoặc memory tăng mất kiểm soát. Với open-loop, tăng arrival rate theo bậc riêng và giữ concurrency tối đa ở client để bảo vệ load generator.

Một giới hạn vận hành nên được xác định từ nhiều điều kiện:

- Throughput thành công vẫn tăng hoặc ổn định theo mục tiêu.
- p95/p99 latency nằm trong SLO.
- Error, timeout, cancel và reconnect nằm trong giới hạn chấp nhận.
- In-flight interactions và queue không tăng liên tục qua thời gian.
- Heap sau GC, direct memory, RSS và cgroup usage không tiến gần giới hạn theo xu hướng không an toàn.
- GC pause, CPU và event loop vẫn còn dư địa cho burst hợp lý.

Không chọn mức tải ngay tại điểm đầu tiên benchmark còn chạy được. Chọn mức thấp hơn điểm bão hòa để dành headroom cho biến động traffic, deployment, reconnect storm và dependency chậm. Headroom cụ thể cần dựa trên đặc tính tải và SLO của hệ thống.

### Thử nghiệm áp lực bộ nhớ

1. Chạy baseline với payload nhỏ và concurrency thấp; ghi heap, direct memory, RSS và GC.
2. Tăng payload theo bậc nhưng giữ nguyên số interaction đồng thời.
3. Giữ payload và tăng concurrency để kiểm tra số object/buffer sống cùng lúc.
4. Tạo consumer chậm để quan sát queue và backpressure.
5. Dừng phát tải và theo dõi thời gian hệ thống trở về trạng thái idle.
6. Lặp lại nhiều chu kỳ tải/idle để tìm xu hướng tăng bộ nhớ qua mỗi chu kỳ.
7. Chạy một lượt riêng với Netty leak detection nếu số liệu gợi ý rò rỉ buffer.

Nếu heap tăng rồi ổn định sau GC, có thể đó là working set hoặc cache được làm nóng. Nếu heap sau GC tăng qua từng chu kỳ, kiểm tra object retention, cache không giới hạn, subscriber còn sống, queue và collection được giữ tham chiếu. Nếu heap ổn định nhưng RSS/direct memory tiếp tục tăng, kiểm tra Netty allocator, native allocation, thread count và memory mapping.

## 9. Bài thực hành: lập báo cáo capacity

Thực hiện bài thực hành trên một service RSocket có ít nhất một route request-response và một route stream. Nếu chưa có handler nghiệp vụ, dùng bench.echo làm baseline rồi thêm một handler có CPU hoặc dependency mô phỏng. Chạy qua TCP trước, sau đó qua WebSocket nếu ứng dụng hỗ trợ cả hai.

Ghi kết quả vào bảng sau cho từng lượt:

| Trường | Giá trị cần ghi |
|---|---|
| Build / commit / JDK | Phiên bản server, client và JDK |
| Transport / TLS / proxy | TCP hoặc WebSocket, TLS, đường đi qua proxy |
| Kết nối / concurrency | Số session vật lý và interaction đồng thời mỗi session |
| Payload / interaction | Kích thước, codec và request type |
| Offered / completed rate | Request/giây được phát sinh và hoàn tất |
| Latency | p50, p95, p99 và max |
| Errors | Timeout, protocol error, disconnect, reconnect |
| CPU / network | CPU client/server và byte gửi/nhận |
| Memory / GC | Heap sau GC, direct buffer, RSS, GC pause |
| Kết luận | Bottleneck, mức tải bền vững và headroom đã chọn |

Sau khi chạy, trả lời các câu hỏi:

1. Khi tăng concurrency, throughput tăng đến mức nào và p99 bắt đầu tăng ở đâu?
2. Một session có đạt giới hạn trước nhiều session không? Điều đó nói gì về multiplexing và phân phối kết nối?
3. Payload lớn làm CPU, network và memory thay đổi ra sao?
4. Khi consumer chậm, queue có bị giới hạn không? Backpressure có truyền ngược tới publisher không?
5. Heap sau GC và direct memory có ổn định sau nhiều chu kỳ tải/idle không?
6. Dấu vết JFR cho thấy thời gian chủ yếu nằm ở handler, codec, event loop hay dependency?
7. Mức concurrency nào đáp ứng SLO và còn headroom phù hợp?

## 10. Checklist trước khi công bố kết quả

- [ ] Dùng RSocket client thật và đúng transport, route, codec, metadata, TLS.
- [ ] Ghi rõ closed-loop hay open-loop; có offered rate và completed throughput.
- [ ] Tách số kết nối vật lý khỏi concurrency interaction.
- [ ] Có warm-up, thời gian đo ổn định và nhiều lần chạy lặp lại.
- [ ] Theo dõi đồng thời client, server, proxy và dependency.
- [ ] Báo cáo p50/p95/p99, lỗi, timeout, reconnect và in-flight.
- [ ] Theo dõi heap, GC, direct buffer, Netty allocator, RSS và cgroup.
- [ ] Kiểm tra queue và backpressure với consumer chậm.
- [ ] Dùng JFR hoặc profiler để xác nhận bottleneck trước khi điều chỉnh.
- [ ] Ghi lại JVM flags, container limit, phiên bản và workload để tái lập.
- [ ] Chọn capacity dưới điểm bão hòa và ghi rõ headroom cùng SLO.

Một benchmark hữu ích phải cho biết hệ thống hoàn tất được bao nhiêu interaction trong điều kiện đã mô tả, latency phân phối ra sao và tài nguyên tăng như thế nào khi tải thay đổi. Dùng cùng workload để đo lại sau mỗi tối ưu; chỉ kết luận cải thiện khi throughput, tail latency, lỗi và memory đều được đối chiếu trong cùng điều kiện.
