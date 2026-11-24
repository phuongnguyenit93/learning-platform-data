# Thiết kế phép đo theo kích thước payload, số kết nối và số luồng

Hiệu năng RSocket không thể được đánh giá chỉ bằng một con số request/giây. Một hệ thống có thể xử lý rất tốt nhiều request nhỏ trên một connection đã mở, nhưng suy giảm khi payload lớn, số connection tăng nhanh hoặc nhiều stream dài hạn cùng hoạt động.

Muốn kết quả đo có ý nghĩa, cần kiểm soát ba nhóm tải độc lập:

1. **Payload size:** số byte data và metadata được gửi trong mỗi interaction.
2. **Connection count:** số TCP/WebSocket connection và RSocket session đang mở đồng thời, cùng tốc độ mở/đóng connection.
3. **Stream count:** số interaction đang hoạt động, số stream trên mỗi connection và số payload mỗi stream phát/nhận.

Ba biến này tác động lên các tài nguyên khác nhau. Payload lớn làm tăng băng thông, copy, encode/decode và bộ nhớ đệm. Nhiều connection làm tăng socket, TLS state, event-loop bookkeeping và bộ nhớ nền. Nhiều stream trên một connection làm tăng state, subscription, demand và công việc multiplex. Phép đo tốt phải thay đổi từng biến có chủ đích, sau đó mới kiểm tra các tổ hợp thực tế.

## 1. Mục tiêu của phép đo hiệu năng

Một benchmark RSocket cần trả lời các câu hỏi cụ thể:

- Server giữ được bao nhiêu connection ổn định?
- Mỗi connection có thể multiplex bao nhiêu stream trước khi latency tăng mạnh?
- Payload tăng từ 1 KB lên 64 KB làm throughput và CPU thay đổi thế nào?
- Request-response và request-stream có profile hiệu năng khác nhau ra sao?
- Khi consumer chậm, backpressure làm giảm throughput hay tạo backlog?
- CPU, heap, direct memory, network và event loop bão hòa ở điểm nào?
- Throughput tối đa còn đáp ứng p95/p99 latency và error rate theo SLO không?

Mục tiêu không chỉ là tìm con số cao nhất. Cần tìm **điểm bão hòa có thể vận hành**, nơi hệ thống vẫn giữ latency, lỗi và tài nguyên trong giới hạn chấp nhận được.

## 2. Phân biệt benchmark, load test và capacity test

| Loại kiểm thử | Mục đích | Ví dụ |
|---|---|---|
| Microbenchmark | Đo một thao tác nhỏ trong môi trường kiểm soát | JSON encode/decode, tạo payload, codec |
| Benchmark interaction | So sánh chi phí của từng interaction model | Request-response so với request-stream |
| Load test | Đo hệ thống dưới tải dự kiến | 500 connection, 2.000 stream |
| Stress test | Tăng tải tới khi hệ thống vượt ngưỡng | Tăng connection/stream cho đến khi p99 hoặc lỗi tăng |
| Capacity test | Tìm tải tối đa vẫn đáp ứng SLO | Số connection và stream bền vững trong giới hạn CPU/memory |
| Soak test | Kiểm tra độ ổn định trong thời gian dài | Giữ tải ổn định vài giờ để tìm leak hoặc drift |
| Spike test | Kiểm tra phản ứng với burst | Tăng đột ngột từ 100 lên 2.000 connection |

Không dùng kết quả microbenchmark codec để kết luận số connection tối đa của server. Một thao tác encode nhanh không chứng minh transport, scheduler, flow control và domain handler có thể chịu tải tương ứng.

## 3. Mô hình tải: ba biến chính

Đặt:

- P là kích thước payload data theo byte.
- C là số connection đang mở.
- S là số stream/interaction đang hoạt động.
- S/C là số stream trung bình trên mỗi connection.
- R là số payload được phát hoặc nhận mỗi giây.
- L là latency của một interaction hoặc một payload.
- B là băng thông payload quan sát được.

Một workload cần mô tả ít nhất:

~~~text
Workload =
  transport
  + payload size distribution
  + active connection count
  + connection open/close rate
  + active stream count
  + interaction model mix
  + payload rate per stream
  + producer/consumer demand
  + business processing cost
~~~

Ví dụ hai workload có cùng 1.000 request/giây nhưng rất khác nhau:

- 1.000 request-response, mỗi payload 256 byte, trên 20 connection.
- 100 request-stream, mỗi stream phát 10 payload/giây, mỗi payload 16 KB, trên 5 connection.

Workload thứ hai có ít interaction mở mới hơn nhưng truyền nhiều byte hơn, giữ nhiều stream state hơn và có vòng đời dài hơn.

## 4. Đo payload size: data và metadata riêng biệt

Payload size cần được đo bằng byte, không chỉ bằng số ký tự hoặc kích thước object trong heap.

Một RSocket payload có data và metadata. Cần ghi nhận riêng:

- Data bytes: nội dung chính của request/response.
- Metadata bytes: route, authentication, tracing hoặc custom metadata.
- Encoded bytes: kích thước sau khi codec serialize.
- Wire bytes: tổng byte thực sự truyền qua transport, bao gồm framing và các phần protocol liên quan.

Các đại lượng này không giống nhau. Ví dụ một DTO Java có thể chiếm 2 KB trong heap nhưng JSON UTF-8 sau encode dài 3 KB. RSocket frame còn có overhead khác; WebSocket/TCP có thể thêm overhead transport.

### Bộ payload test

Nên bắt đầu bằng các mức đại diện, sau đó thay đổi theo giới hạn thực tế của ứng dụng:

| Nhóm | Data payload | Mục đích |
|---|---:|---|
| Tiny | 64–256 B | Metadata, event nhỏ, command đơn giản |
| Small | 1 KB | Request/response thông thường |
| Medium | 8 KB | DTO có nhiều trường |
| Large | 64 KB | Nội dung lớn, batch nhỏ |
| Very large | 256 KB–1 MB | Kiểm tra giới hạn, memory và fragmentation nếu được hỗ trợ/cấu hình |

Không chỉ test một kích thước cố định. Workload thực tế thường có phân phối, ví dụ 70% payload 1 KB, 25% payload 8 KB và 5% payload 64 KB. Một payload lớn hiếm gặp vẫn có thể chi phối p99 latency và memory pressure.

### Những gì cần đo theo payload size

- Encode duration và decode duration.
- Data bytes và metadata bytes.
- Payload throughput theo byte/giây.
- p50/p95/p99 interaction latency theo nhóm payload.
- CPU time và allocation rate.
- Heap/direct memory và GC pause.
- Tỷ lệ lỗi do vượt frame/payload limit.
- Số lần copy hoặc buffer allocation nếu profiler hỗ trợ.

Thông lượng byte có thể ước lượng bằng:

\[
B \approx R \times \overline{P}
\]

Trong đó R là số payload mỗi giây và P trung bình là số byte payload. Đây là payload throughput, chưa gồm protocol/transport overhead và phải tính riêng cho chiều vào, chiều ra.

### Phân phối quan trọng hơn chỉ số trung bình

Nếu phần lớn payload là 1 KB nhưng một nhóm nhỏ là 1 MB, average có thể che giấu chi phí của nhóm lớn. Hãy dùng histogram hoặc DistributionSummary để quan sát percentile, max và count theo route/interaction type có cardinality thấp.

## 5. Đo connection count và connection churn

Connection count là số TCP/WebSocket/RSocket session đang mở tại cùng thời điểm. Cần tách ba đại lượng:

- **Active connections:** số connection đang tồn tại.
- **Connection churn:** tốc độ mở và đóng connection.
- **Connection setup latency:** thời gian từ lúc bắt đầu kết nối đến khi RSocket SETUP hoàn tất.

Một server có thể giữ 10.000 connection lâu dài nhưng gặp khó khăn khi 10.000 client cùng reconnect trong vài giây. Vì vậy, capacity test phải đo cả connection count và open/close rate.

### Các kịch bản connection

| Kịch bản | Mục tiêu |
|---|---|
| Một connection, tăng stream | Đo multiplex và chi phí stream |
| Nhiều connection, ít stream mỗi connection | Đo socket/session overhead |
| Nhiều connection, nhiều stream mỗi connection | Đo tải kết hợp |
| Ramp-up chậm | Tìm giới hạn tăng tải ổn định |
| Connection churn | Đo handshake, TLS và cleanup |
| Reconnect storm | Đo khả năng phục hồi sau outage |
| Idle connection | Đo bộ nhớ nền và keepalive |
| Long-lived connection | Phát hiện resource leak theo thời gian |

TCP và WebSocket cần được benchmark riêng. WebSocket có HTTP upgrade handshake và framing riêng; TLS/WSS thêm chi phí mã hóa. So sánh chỉ có ý nghĩa khi cấu hình TLS, proxy, codec và workload được ghi rõ.

### Tài nguyên theo connection

Theo dõi cùng connection count:

- File descriptors/socket count.
- Heap và direct/native memory.
- TLS session/context memory nếu dùng TLS.
- Event-loop utilization và pending tasks.
- Socket send/receive buffer.
- Connection setup latency và timeout.
- Keepalive timeout, disconnect và reconnect rate.

Không suy ra connection capacity chỉ từ heap. Một số buffer và network allocation có thể nằm ngoài heap; cần quan sát direct memory và container memory.

## 6. Đo stream count và multiplexing

Stream count là số interaction đang hoạt động tại một thời điểm. Nó khác số connection và khác số payload đã truyền.

Một connection có thể mang nhiều stream đồng thời. Vì vậy cần đo:

- Active streams tổng.
- Active streams trên mỗi connection.
- Stream open rate và completion/cancellation rate.
- Stream lifetime.
- Time to first item.
- Items/second theo stream và tổng hệ thống.
- Demand/request-N và số payload thực tế phát.
- Buffer/queue depth và slow-consumer count.

### Ma trận stream test

| Số connection | Stream mỗi connection | Tổng stream |
|---:|---:|---:|
| 1 | 1 | 1 |
| 1 | 10 | 10 |
| 1 | 100 | 100 |
| 10 | 10 | 100 |
| 100 | 10 | 1.000 |
| 100 | 50 | 5.000 |
| 500 | 20 | 10.000 |

Đây là các điểm thử minh họa, không phải giới hạn mặc định của RSocket. Giới hạn thực tế phụ thuộc server, transport, workload, tài nguyên và cấu hình.

Để cô lập chi phí multiplex, so sánh hai workload có cùng tổng số stream:

- 100 connection × 1 stream.
- 1 connection × 100 stream.

Tổng stream giống nhau nhưng số socket, state connection và cách phân bổ event-loop khác nhau.

## 7. Phân biệt interaction count, stream count và payload count

Các số đếm sau không thể thay thế cho nhau:

- Một request-response thường có một interaction và một response payload.
- Một request-stream có một interaction nhưng nhiều response payload.
- Một request-channel có một interaction với nhiều payload ở cả hai hướng.
- Fire-and-forget không có response payload để xác nhận nghiệp vụ.

Khi benchmark, cần ghi:

| Chỉ số | Đơn vị |
|---|---|
| Interaction rate | interaction/giây |
| Stream concurrency | stream đang hoạt động |
| Payload rate | payload/giây |
| Byte throughput | byte/giây |
| Business throughput | thao tác nghiệp vụ hoàn tất/giây |

Ví dụ request-stream phát 500 item/giây trên 10 stream có thể tạo 5.000 payload/giây nhưng chỉ có 10 interaction đang hoạt động. Nếu chỉ nhìn request rate, tải thực tế sẽ bị đánh giá thấp.

## 8. Interaction model ảnh hưởng profile hiệu năng

Nên benchmark từng interaction model riêng trước khi chạy workload hỗn hợp.

| Interaction | Chi phí cần quan sát |
|---|---|
| Request-response | Round-trip latency, encode/decode hai chiều, handler duration |
| Fire-and-forget | Inbound throughput, queueing, xử lý bất đồng bộ và xác nhận nghiệp vụ |
| Request-stream | Time to first item, items/second, stream lifetime, cancellation |
| Request-channel | Throughput hai chiều, demand độc lập, buffering và xử lý đồng thời |

Request-response thường phù hợp để đo round-trip latency. Request-stream cần đo cả thời gian tới item đầu tiên và tốc độ phát. Request-channel cần đo hai hướng riêng vì producer và consumer có thể có tốc độ khác nhau.

Với fire-and-forget, thời điểm client hoàn tất thao tác gửi không chứng minh server đã xử lý xong. Nếu cần business throughput, hãy đếm ở phía server sau khi nghiệp vụ hoàn tất hoặc commit.

## 9. Latency: đo đúng điểm bắt đầu và kết thúc

Latency có thể được đo ở nhiều ranh giới:

- Client-side round-trip latency: từ lúc gửi request đến khi nhận response.
- Server handler latency: từ lúc handler bắt đầu đến khi kết quả được phát.
- Setup latency: thời gian mở connection và hoàn tất SETUP.
- Time to first item: thời gian từ lúc mở stream đến payload đầu tiên.
- Inter-arrival time: khoảng cách giữa các payload liên tiếp.
- Stream lifetime: từ lúc interaction bắt đầu đến complete/error/cancel.
- Business latency: từ lúc nhận command đến khi transaction nghiệp vụ commit.

Không trộn các loại latency trong cùng một metric. Nếu đo từ client, latency có thể gồm network, queue, server, response network và scheduler. Nếu đo trong handler, latency không bao gồm toàn bộ round trip.

### Dùng percentile thay vì chỉ dùng average

Nên báo cáo:

- p50: trải nghiệm trung vị.
- p90/p95: phần lớn request.
- p99/p99.9: tail latency.
- max: trường hợp chậm nhất trong cửa sổ đo.
- error/timeout rate: tỷ lệ request không hoàn tất đúng hợp đồng.

Average thấp vẫn có thể đi cùng p99 rất cao. Tail latency thường tăng khi connection, stream, queue hoặc dependency tiến gần bão hòa.

## 10. Throughput và giới hạn tải

Throughput phải gắn với đơn vị:

- Requests/second.
- Interactions/second.
- Payloads/second.
- MB/second.
- Business operations/second.

Không so sánh 10.000 payload/giây với 10.000 request/giây nếu mỗi request-stream phát nhiều payload.

Một hệ thống có thể tăng throughput khi thêm concurrency, nhưng sau một điểm latency và error rate sẽ tăng nhanh. Đó là vùng bão hòa. Capacity nên được chọn trước điểm này và có headroom cho burst, failover và reconnect.

### Dùng Little's Law để ước lượng concurrency

Với hệ thống ổn định, quan hệ gần đúng:

\[
L = \lambda W
\]

Trong đó:

- L là số interaction trung bình đang in-flight.
- λ là throughput hoàn tất mỗi giây.
- W là latency trung bình tính bằng giây.

Ví dụ hệ thống hoàn tất 2.000 request/giây với latency trung bình 50 ms:

\[
L = 2000 \times 0.05 = 100
\]

Có khoảng 100 request đang in-flight trung bình. Đây là ước lượng theo điều kiện ổn định, không phải giới hạn stream tối đa và không thay thế phép đo thực tế.

## 11. Resource metrics phải đo cùng lúc

Một benchmark chỉ ghi throughput và latency sẽ không giải thích được vì sao hệ thống suy giảm. Nên thu thập đồng thời:

| Tài nguyên | Chỉ số |
|---|---|
| CPU | Process/container CPU, CPU throttling |
| Heap | Used/committed heap, allocation rate |
| GC | Pause duration, frequency, promotion |
| Native/direct memory | Direct buffer usage, process RSS |
| Network | Bytes in/out, packet rate, retransmits, socket errors |
| Event loop | Busy time, pending tasks, blocked thread detection |
| Scheduler | Active workers, queue depth, rejected tasks |
| Database | Pool active/idle, wait time, query latency |
| Downstream | Request rate, latency, timeout/error |
| Reactor | Queue/buffer, dropped signals, cancellation |

Không chỉ đo trên server. Load generator có thể trở thành bottleneck trước server do CPU, socket, NIC hoặc giới hạn ephemeral ports. Dùng nhiều máy phát tải nếu cần và kiểm tra tài nguyên của chúng.

## 12. Thiết kế workload matrix

Không nên chạy mọi tổ hợp của payload size × connections × streams × interaction type × transport ngay từ đầu. Số tổ hợp tăng rất nhanh.

Có thể chia thành ba giai đoạn:

**Giai đoạn A – Cô lập từng biến**

| Test | Payload | Connections | Streams |
|---|---|---:|---:|
| P1 | 256 B | 1 | 1 |
| P2 | 1 KB | 1 | 1 |
| P3 | 8 KB | 1 | 1 |
| P4 | 64 KB | 1 | 1 |
| C1 | 1 KB | 10 | 1 |
| C2 | 1 KB | 100 | 1 |
| C3 | 1 KB | 500 | 1 |
| S1 | 1 KB | 1 | 10 |
| S2 | 1 KB | 1 | 100 |
| S3 | 1 KB | 10 | 100 |

**Giai đoạn B – Tổ hợp thực tế**

Chọn một vài profile dựa trên production traffic, ví dụ:

- Nhiều connection nhỏ, ít stream mỗi connection.
- Ít connection nhưng nhiều stream multiplex.
- Payload hỗn hợp và request-response chủ yếu.
- Request-stream dài hạn, tốc độ payload ổn định.
- Request-channel hai chiều với consumer chậm.

**Giai đoạn C – Biên và phục hồi**

- Payload gần giới hạn cấu hình.
- Connection count gần capacity.
- Stream count gần saturation.
- Burst/reconnect storm.
- Slow consumer và cancellation.
- Server restart hoặc downstream chậm.

## 13. Các pha của một lần benchmark

Một lần đo nên có các pha được xác định trước:

~~~mermaid
flowchart LR
    A[Baseline] --> B[Warm-up]
    B --> C[Ramp-up]
    C --> D[Steady-state]
    D --> E[Spike / Stress]
    E --> F[Recovery]
    F --> G[Soak]
    G --> H[Report]
~~~

| Pha | Mục tiêu | Cách thực hiện |
|---|---|---|
| Baseline | Xác định trạng thái ban đầu | Không tải hoặc tải rất thấp |
| Warm-up | Cho JVM/JIT/cache ổn định | Chạy tải đại diện, không lấy số đo chính |
| Ramp-up | Tăng tải có kiểm soát | Tăng connection/stream theo từng bước |
| Steady-state | Đo năng lực ổn định | Giữ tải cố định trong cửa sổ đủ dài |
| Spike/stress | Xác định phản ứng ở tải cao | Tăng nhanh hoặc vượt capacity dự kiến |
| Recovery | Đo khả năng trở lại bình thường | Giảm tải, quan sát queue và resource |
| Soak | Tìm leak và suy giảm theo thời gian | Giữ tải đại diện trong thời gian dài |
| Report | Tổng hợp kết quả | Ghi môi trường, config, percentile và giới hạn |

Warm-up rất quan trọng với JVM vì JIT compilation, class loading, connection pool và cache có thể làm các lần chạy đầu chậm hơn. Không lấy số đo warm-up làm baseline hiệu năng.

## 14. Open-loop và closed-loop load generation

Hai cách tạo tải cho kết quả khác nhau:

- **Closed-loop:** client gửi request mới sau khi request trước hoàn tất. Khi server chậm, tốc độ tạo request tự giảm.
- **Open-loop:** client phát request theo arrival rate định trước, độc lập với thời gian phản hồi. Khi server chậm, backlog và latency sẽ bộc lộ rõ hơn.

Closed-loop dễ dùng nhưng có thể che giấu overload vì generator tự giảm tốc. Open-loop phù hợp khi cần kiểm tra hệ thống dưới arrival rate cố định, nhưng phải có giới hạn backlog và cách xử lý khi generator không theo kịp.

Dùng cả hai nếu workload production có cả người dùng tương tác và event producer phát theo tốc độ cố định. Ghi rõ mô hình trong báo cáo để so sánh đúng.

## 15. Giữ workload ổn định và tránh coordinated omission

Coordinated omission xảy ra khi load generator chỉ đo request tiếp theo sau khi request trước hoàn tất. Khi server bị chậm, generator gửi ít request hơn và bỏ qua những khoảng thời gian mà request lẽ ra phải được gửi. Latency báo cáo có thể đẹp hơn thực tế.

Để giảm sai lệch:

- Với open-loop, lên lịch request theo arrival time độc lập.
- Ghi cả scheduled time và actual send time.
- Báo cáo queueing delay tại client nếu generator bị chậm.
- Dùng histogram có thể ghi nhận latency theo workload model phù hợp.
- Không bỏ qua timeout hoặc request chưa hoàn tất khi tổng hợp.
- Kiểm tra CPU/network của load generator.

Nếu generator không thể duy trì arrival rate đã đặt, benchmark đó không còn đại diện cho workload dự kiến.

## 16. Đo payload với codec thực tế

Payload test cần dùng cùng serializer, MIME type và schema như ứng dụng production. Nếu production dùng JSON nhưng benchmark gửi byte array thô, kết quả chỉ đo transport cho byte array, không đo chi phí JSON encode/decode.

Các yếu tố cần cố định:

- Codec và phiên bản.
- Data MIME type và metadata MIME type.
- Kích thước sau serialize.
- Compression có bật hay không.
- Schema và độ sâu object.
- Số trường, collection length và chuỗi Unicode.
- Tỷ lệ payload hợp lệ/lỗi.
- Payload fragmentation hoặc frame size nếu cấu hình có liên quan.

Ví dụ đo kích thước JSON trước khi gửi:

~~~java
byte[] encoded = objectMapper.writeValueAsBytes(request);
payloadSizeSummary.record(encoded.length);
~~~

Đoạn này chỉ cho biết kích thước JSON do ObjectMapper tạo. Nếu RSocket requester dùng codec hoặc ObjectMapper khác, số byte thực tế có thể khác. Muốn đo wire payload, instrument tại codec/frame boundary hoặc dùng capture/metrics ở transport phù hợp.

## 17. Ví dụ ghi Timer và DistributionSummary

Một lớp metrics có thể ghi latency và payload size:

~~~java
@Component
public class RSocketPerformanceMetrics {

    private final MeterRegistry registry;
    private final Timer interactionTimer;
    private final DistributionSummary payloadBytes;

    public RSocketPerformanceMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.interactionTimer = Timer.builder(
                "rsocket.benchmark.interaction.duration")
            .description("RSocket interaction duration")
            .tag("route", "benchmark.echo")
            .register(registry);

        this.payloadBytes = DistributionSummary.builder(
                "rsocket.benchmark.payload.bytes")
            .baseUnit("bytes")
            .description("Encoded data payload size")
            .register(registry);
    }

    public <T> Mono<T> measure(
            Mono<T> operation,
            int encodedPayloadBytes) {

        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(registry);

            payloadBytes.record(encodedPayloadBytes);

            return operation.doFinally(signal ->
                sample.stop(interactionTimer));
        });
    }
}
~~~

Ví dụ đo thời gian từ lúc subscription bắt đầu đến terminal signal. Nếu cần tách success/error/cancel, hãy dùng tag outcome có tập giá trị cố định và đăng ký Timer tương ứng. Không thêm requestId, connectionId hoặc streamId làm tag metric vì cardinality sẽ tăng theo từng interaction.

## 18. Tạo nhiều stream trên một RSocket connection

Với Spring RSocketRequester, một requester có thể được dùng lại để mở nhiều interaction trên connection đã thiết lập. Có thể dùng flatMap với concurrency để tạo nhiều stream đồng thời:

~~~java
Flux<BenchEvent> runConcurrentStreams(
        RSocketRequester requester,
        int streamCount,
        int itemsPerStream) {

    return Flux.range(0, streamCount)
        .flatMap(streamIndex ->
            requester
                .route("benchmark.stream")
                .data(new BenchStreamRequest(
                    streamIndex,
                    itemsPerStream))
                .retrieveFlux(BenchEvent.class)
                .take(itemsPerStream),
            streamCount
        );
}
~~~

Đoạn này minh họa việc multiplex nhiều request-stream trên một requester. streamCount là số stream được tạo; concurrency của flatMap giới hạn số publisher inner được subscribe đồng thời. Nếu mỗi stream kết thúc sau itemsPerStream phần tử, tổng thời gian test còn phụ thuộc tốc độ producer và consumer.

Để kiểm tra nhiều connection, cần tạo nhiều client/requester độc lập và phân phối stream qua chúng. Không tăng số requester bằng cách tạo mới cho từng payload nếu mục tiêu là đo multiplex trên connection lâu dài.

## 19. Đo request-channel hai chiều

Request-channel cần đo riêng inbound và outbound:

- Request items/second từ client đến server.
- Response items/second từ server về client.
- Demand mỗi hướng.
- Thời gian xử lý command.
- Response latency và queueing.
- Số phần tử buffer khi một phía chậm.

Không gộp tổng bytes hai chiều thành một con số nếu cần xác định bottleneck. Ví dụ client gửi command 1 KB nhưng server trả snapshot 64 KB; outbound bandwidth có thể là giới hạn.

Một workload channel tốt nên có ít nhất ba tình huống:

1. Hai phía có tốc độ gần bằng nhau.
2. Client gửi nhanh, server xử lý chậm.
3. Server phát response nhanh, client tiêu thụ chậm.

Khi một phía chậm, kiểm tra demand, bounded buffer, cancellation và resource usage. Backpressure điều tiết số phần tử theo demand nhưng không giới hạn byte của một payload.

## 20. Đo tải kết hợp với business processing

Benchmark chỉ echo payload đo được transport và codec nhưng không phản ánh chi phí nghiệp vụ. Nên có ít nhất hai nhóm:

- **Transport/codec benchmark:** handler trả lại hoặc biến đổi payload đơn giản để đo overhead của RSocket và codec.
- **Business benchmark:** handler gọi service/database/downstream giống production để đo end-to-end capacity.

Không trộn kết quả hai nhóm. Nếu benchmark business phụ thuộc database, hãy ghi rõ connection pool, dataset, cache state và query plan. Nếu dùng mock downstream, ghi rõ đó là synthetic workload.

## 21. Xác định điểm bão hòa

Điểm bão hòa thường xuất hiện khi một hoặc nhiều tài nguyên tiến gần giới hạn:

- CPU gần 100% hoặc bị container throttling.
- Heap/direct memory tăng liên tục.
- GC pause và allocation rate tăng.
- Event loop có pending tasks hoặc bị block.
- Queue depth tăng dù throughput không tăng.
- p95/p99 latency tăng nhanh.
- Timeout, reset hoặc rejected execution tăng.
- Throughput hoàn tất không còn tăng khi thêm connection/stream.

Đừng chỉ chọn điểm có throughput cao nhất. Chọn mức tải còn giữ được SLO, có headroom và phục hồi được sau burst.

### Headroom

Nếu capacity đo được tại điểm SLO là 10.000 interaction/giây, không nên mặc định production luôn chạy ở 10.000. Cần dành headroom cho burst, deploy, node failure và reconnect storm. Mức headroom cụ thể dựa trên biến động traffic và mục tiêu availability của hệ thống.

## 22. So sánh TCP và WebSocket

Để so sánh transport:

- Dùng cùng payload distribution.
- Dùng cùng số connection và stream.
- Dùng cùng interaction mix.
- Dùng cùng codec và business handler.
- Cố định TLS/WSS và proxy topology.
- Chạy warm-up và steady-state tương đương.
- Đo cả client và server.

WebSocket có handshake HTTP upgrade và framing; TCP transport có lifecycle kết nối khác. Nếu so sánh WSS với TCP không mã hóa, kết quả không phản ánh đúng trade-off bảo mật và triển khai production.

Ghi riêng setup latency và steady-state latency. Chi phí handshake lớn có thể bị che khuất nếu chỉ đo request trên connection đã mở sẵn.

## 23. Báo cáo kết quả benchmark

Một báo cáo có thể dùng cấu trúc:

~~~text
Environment:
  application version:
  JDK / JVM:
  Spring Framework / RSocket version:
  transport: TCP | WebSocket | WSS
  TLS: enabled | disabled
  codec / MIME type:
  server CPU / memory:
  client generator nodes:

Workload:
  payload distribution:
  data bytes / metadata bytes:
  active connections:
  connection open rate:
  active streams:
  streams per connection:
  interaction mix:
  arrival rate:
  duration:

Results:
  interactions per second:
  payloads per second:
  business operations per second:
  payload MB/s in/out:
  p50 / p95 / p99 latency:
  time to first item:
  error / timeout / cancel rate:
  CPU / heap / direct memory:
  network throughput:
  queue depth / consumer lag:

Conclusion:
  saturation point:
  limiting resource:
  safe operating range:
  headroom:
  known limitations:
~~~

Báo cáo phải ghi cả cấu hình và workload. Một con số “RSocket đạt 50.000 request/giây” không có ý nghĩa nếu không biết payload size, connection count, stream count, interaction type, TLS, latency và phần cứng.

## 24. Checklist trước khi chạy benchmark

- Đã xác định mục tiêu: latency, throughput, capacity hay soak.
- Đã ghi payload distribution theo byte.
- Đã tách data size và metadata size.
- Đã cố định codec, MIME type và transport.
- Đã xác định số connection và connection churn.
- Đã xác định số stream tổng và stream trên mỗi connection.
- Đã xác định interaction model mix.
- Đã đo payload rate và byte throughput.
- Đã cấu hình warm-up, ramp-up và steady-state.
- Đã chọn open-loop hoặc closed-loop và ghi rõ.
- Load generator không phải bottleneck.
- Đã thu thập CPU, heap, direct memory, GC và network.
- Đã đo p50/p95/p99, error rate và cancellation.
- Đã xác định SLO và điểm bão hòa.
- Đã lặp lại benchmark để kiểm tra độ ổn định.

## 25. Kết luận

Thiết kế phép đo hiệu năng RSocket cần tách kích thước payload, số connection và số stream vì mỗi biến tạo áp lực lên một nhóm tài nguyên khác nhau. Payload ảnh hưởng băng thông, codec và memory; connection ảnh hưởng socket, handshake và trạng thái phiên; stream ảnh hưởng multiplexing, demand, buffer và concurrency.

Hãy đo riêng từng biến, sau đó chạy workload kết hợp theo traffic thực tế. Kết hợp latency percentile, throughput, error rate, CPU, heap/direct memory, network và queue depth để tìm điểm bão hòa. Một benchmark có thể lặp lại phải ghi rõ transport, codec, payload distribution, connection count, stream count, interaction mix và mô hình tạo tải.

Kết quả có giá trị không phải là con số throughput lớn nhất, mà là vùng tải hệ thống có thể duy trì ổn định, đáp ứng SLO và còn đủ headroom để phục hồi khi traffic tăng hoặc một thành phần gặp sự cố.

Tài liệu tham khảo:
- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [Spring Framework Reference – RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/)
- [Micrometer Reference](https://docs.micrometer.io/micrometer/reference/)
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/)

