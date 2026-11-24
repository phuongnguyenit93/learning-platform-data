# Kiểm thử tải kéo dài, nhiều bên nhận chậm và ngắt kết nối hàng loạt

Một hệ thống RSocket có thể xử lý tốt bài benchmark ngắn nhưng suy giảm sau nhiều giờ chạy. Buffer tăng dần, direct memory không được giải phóng, số stream tồn tại lâu hơn dự kiến, subscriber chậm làm producer bị nghẽn, hoặc một đợt mất mạng khiến hàng nghìn client reconnect cùng lúc. Các vấn đề này thường không xuất hiện trong bài test chỉ gửi request-response trong vài phút.

Để đánh giá độ bền, cần kết hợp ba loại thử nghiệm: **soak test** chạy tải ổn định trong thời gian dài, **slow-consumer test** tạo nhiều bên nhận có tốc độ xử lý thấp, và **mass-disconnect test** chủ động ngắt nhiều connection rồi quan sát quá trình phục hồi. Các bài test phải đo cả throughput, latency, backpressure, buffer, memory, connection churn và thời gian trở lại trạng thái ổn định.

Bài học này tập trung vào RSocket chạy trên TCP hoặc WebSocket, với client/server Java và Spring Boot. Mục tiêu là phát hiện điểm nghẽn và rò rỉ tài nguyên trước khi chúng trở thành sự cố production.

Sau bài học, bạn có thể:

- Thiết kế workload dài hạn với tốc độ phát và phân bố interaction thực tế.
- Phân biệt load test, stress test, soak test và spike test.
- Mô phỏng nhiều subscriber chậm và quan sát backpressure.
- Chọn buffer có giới hạn, drop, reject hoặc persist theo semantics dữ liệu.
- Kiểm thử hủy stream và giải phóng tài nguyên khi client rời đi.
- Mô phỏng mất kết nối hàng loạt, reconnect storm và RSocket resume.
- Đo memory, direct memory, GC, event loop, socket và queue trong thời gian dài.
- Đặt SLO và tiêu chí pass/fail cho throughput, latency, error rate và recovery.
- Xây dựng kịch bản kiểm thử lặp lại được và phân tích kết quả theo từng pha.

## 1. Vì sao cần kiểm thử tải kéo dài?

Load test ngắn thường tập trung vào khả năng xử lý request trong điều kiện hệ thống đã warm-up. Nó ít phát hiện những vấn đề tích lũy theo thời gian:

- Buffer tăng vì producer liên tục nhanh hơn consumer.
- Subscriber bị treo hoặc quên cancel làm stream và state tồn tại mãi.
- ByteBuf/direct memory không được release đúng cách.
- Connection pool tạo connection mới nhưng không dispose connection cũ.
- Retry và reconnect đồng loạt làm tăng tải sau mỗi lần sự cố.
- Cache, metric label hoặc session registry tăng không giới hạn.
- GC pause tăng dần khi heap và allocation rate tăng.
- Queue có giới hạn quá lớn, khiến hệ thống chỉ trì hoãn lỗi thay vì xử lý được tải.

Một soak test phải chạy đủ lâu để các xu hướng này bộc lộ. Thời lượng phụ thuộc mục tiêu và môi trường; có thể bắt đầu bằng 1–2 giờ ở môi trường dev, sau đó chạy 8–24 giờ hoặc lâu hơn trong môi trường staging gần production. Thời gian ngắn hơn có thể dùng để tìm lỗi sớm, nhưng không nên gọi là bằng chứng đầy đủ cho độ bền dài hạn.

~~~mermaid
flowchart LR
    A[Warm-up] --> B[Steady soak load]
    B --> C[Increase slow consumers]
    C --> D[Mass disconnect]
    D --> E[Reconnect / resume]
    E --> F[Recovery steady state]
    F --> G[Drain and inspect]
~~~

Mỗi pha trả lời một câu hỏi khác nhau:

| Pha | Câu hỏi |
|---|---|
| Warm-up | JVM, JIT, connection pool và cache đã ổn định chưa? |
| Steady soak | Tải bình thường có giữ ổn định qua thời gian không? |
| Slow consumers | Backpressure và buffer có được kiểm soát không? |
| Mass disconnect | Hệ thống chịu được số lượng lớn connection rời đi không? |
| Reconnect/resume | Client quay lại có tạo reconnect storm hoặc mất state không? |
| Recovery | Sau sự cố, latency và resource có trở về baseline không? |
| Drain | Stream, socket, buffer và task còn sót lại không? |

## 2. Phân biệt các loại kiểm thử hiệu năng

| Loại test | Mục đích | Cách tạo tải |
|---|---|---|
| Load test | Xác nhận SLO ở tải dự kiến | Tải tăng tới mức production mục tiêu |
| Stress test | Tìm giới hạn và hành vi khi quá tải | Tăng vượt capacity |
| Soak test | Phát hiện suy giảm/rò rỉ theo thời gian | Tải ổn định nhiều giờ |
| Spike test | Kiểm tra phản ứng với burst | Tăng tải đột ngột rồi giảm |
| Slow-consumer test | Kiểm tra backpressure và queue | Một phần subscriber xử lý chậm |
| Connection-churn test | Kiểm tra chi phí mở/đóng socket | Tạo kết nối và ngắt liên tục |
| Mass-disconnect test | Kiểm tra sự cố mất kết nối diện rộng | Ngắt một tỷ lệ lớn client cùng lúc |
| Recovery test | Đo thời gian trở lại bình thường | Khôi phục mạng/server sau sự cố |

Không nên gộp tất cả thành một bài test duy nhất rồi chỉ nhìn throughput trung bình. Nếu throughput giảm sau mass disconnect, cần biết nguyên nhân là handshake, TLS, SETUP, resume buffer, CPU, event loop hay database.

## 3. Xây dựng mô hình workload thực tế

Trước khi chạy test, xác định profile traffic:

- Số client đồng thời.
- Số RSocket connection trên mỗi client.
- Số interaction đồng thời trên mỗi connection.
- Tỷ lệ request-response, fire-and-forget, request-stream và request-channel.
- Tốc độ producer và kích thước payload.
- Số subscriber và phân bố tốc độ xử lý.
- Tỷ lệ subscriber hủy stream hoặc mất mạng.
- Tần suất reconnect bình thường.
- Thời gian sống trung bình của connection và stream.
- Phân bố request cost và thời gian xử lý.

Ví dụ profile cho một hệ thống giá realtime:

| Thành phần | Profile mẫu |
|---|---:|
| Client đồng thời | 5.000 |
| RSocket connection/client | 1 |
| Subscriber nhận giá | 4.000 |
| Subscriber chậm | 10% subscriber |
| Subscriber rất chậm | 2% subscriber |
| Event producer | 2.000 event/giây |
| Payload trung bình | 512 bytes |
| Soak steady-state | 8 giờ |
| Mass disconnect | 50% client trong 30 giây |
| Recovery target | Trở về SLO trong 5 phút |

Đây chỉ là ví dụ để định hình workload. Số liệu production phải lấy từ traffic thật, capacity mục tiêu và SLO của hệ thống.

### Closed workload và open workload

Closed workload giữ số virtual user cố định: một client hoàn thành request rồi mới gửi request tiếp theo. Khi latency tăng, tốc độ gửi request tự giảm. Mô hình này có thể che giấu quá tải vì chính client giảm tốc khi server chậm.

Open workload tạo request theo arrival rate đã định, độc lập với latency của request trước đó. Nó phù hợp để kiểm tra hệ thống có chịu được tốc độ event/request đầu vào như production hay không.

| Mô hình | Hành vi | Khi phù hợp |
|---|---|---|
| Closed | Số client cố định, client chờ response | Client tương tác và request-response tuần tự |
| Open | Arrival rate cố định hoặc theo lịch | Event ingestion, telemetry, broadcast |
| Hybrid | Client cố định và một phần arrival rate độc lập | Workload realtime pha trộn |

Khi dùng open workload, cần giới hạn số request đang chờ và ghi nhận backlog. Nếu generator không phát đủ tốc độ yêu cầu vì bản thân nó hết tài nguyên, test không còn phản ánh tải dự kiến. Theo dõi CPU, network và queue của load generator riêng với server.

## 4. Chuẩn bị môi trường và dữ liệu kiểm thử

Môi trường test cần tương đồng với production ở các điểm ảnh hưởng tới hiệu năng:

- Phiên bản JDK, Spring, Reactor, RSocket và Netty.
- CPU, RAM, container limits và JVM flags.
- Số replica và cấu hình connection pool.
- TCP backlog, file descriptor và socket buffer.
- TLS/WSS, proxy và idle timeout nếu production có sử dụng.
- Database, broker và dependency mà handler gọi.
- Payload size, metadata size và phân bố route.
- Logging, tracing và metrics được bật ở mức gần production.

Không dùng mock server cho toàn bộ bài soak nếu mục tiêu là đo direct memory, TCP socket, WebSocket, TLS hoặc Netty event loop. Mock có thể dùng để cô lập logic selection, nhưng cần integration test qua transport thật.

### Dữ liệu kiểm thử

Tạo payload có kích thước và phân bố gần production:

- Payload nhỏ thường xuyên.
- Payload trung bình.
- Một tỷ lệ nhỏ payload lớn.
- Metadata route, tenant và correlation.
- Event có sequence để phát hiện mất/lặp.
- Request ID để nối log và đo end-to-end latency.

Không tạo payload ngẫu nhiên quá nặng ngay trên hot path của load generator. Sinh trước fixture hoặc dùng seed cố định để tránh CPU của generator trở thành nút thắt.

## 5. Thiết kế pha soak test

Một kịch bản soak nên có warm-up, steady state, các pha thay đổi có chủ đích và drain.

Ví dụ lịch chạy 8 giờ:

| Giai đoạn | Thời lượng | Tải |
|---|---:|---|
| Warm-up | 15 phút | 20% tải mục tiêu |
| Ramp-up | 15 phút | Tăng từ 20% lên 100% |
| Steady 1 | 2 giờ | 100% tải mục tiêu |
| Slow-consumer phase | 1 giờ | 10% subscriber chậm |
| Steady 2 | 2 giờ | Trở lại profile bình thường |
| Disconnect phase | 30 phút | Ngắt 50% client theo nhiều đợt |
| Recovery phase | 1 giờ | Reconnect/resume và ổn định |
| Final soak | 1 giờ | 100% tải mục tiêu |
| Drain | 15 phút | Hủy stream, đóng connection, thu thập số liệu |

Lịch này là ví dụ. Test dài hơn cần điều chỉnh theo thời gian giữ connection, chu kỳ batch, GC và hoạt động định kỳ của ứng dụng.

Không chỉ ghi một kết quả tổng. Lưu metric theo từng pha để so sánh:

- Baseline trước khi gây lỗi.
- Trong lúc slow consumer.
- Trong lúc disconnect.
- Trong lúc reconnect/resume.
- Sau khi tải đã phục hồi.

## 6. Mô phỏng nhiều bên nhận chậm

Slow consumer xảy ra khi server phát dữ liệu nhanh hơn subscriber có thể xử lý. Trong RSocket request-stream, requester gửi demand bằng REQUEST_N; responder phải tôn trọng demand và không được tùy tiện đẩy response vượt quá giới hạn protocol.

Tuy nhiên, nguồn imperative trong server có thể vẫn tiếp tục tạo event. Nếu ứng dụng nối nguồn đó vào Reactor Sinks hoặc một queue, phần chênh lệch tốc độ có thể tích tụ ở buffer.

~~~mermaid
flowchart LR
    A[Fast event producer] --> B[Publisher / Sink]
    B --> C[Buffer]
    C --> D[RSocket responder]
    D --> E[Fast client]
    D --> F[Slow client]
    D --> G[Very slow client]
    F --> H[Demand falls behind]
    H --> C
    G --> H
~~~

Một bài test nên tạo nhiều nhóm consumer:

| Nhóm | Tốc độ xử lý | Mục đích |
|---|---|---|
| Fast | Nhanh hơn tốc độ phát trung bình | Baseline |
| Normal | Xấp xỉ tốc độ phát | Workload phổ biến |
| Slow | Chậm hơn producer | Kiểm tra buffer/backpressure |
| Very slow | Gần như không request hoặc xử lý rất chậm | Kiểm tra giới hạn và timeout |
| Disconnecting | Hủy stream giữa chừng | Kiểm tra cleanup |

Không chỉ làm chậm tất cả client cùng lúc. Production thường có phân bố: phần lớn client bình thường, một phần chậm do mạng hoặc thiết bị, một phần bị treo và một phần ngắt kết nối.

### Ví dụ tạo subscriber chậm bằng Reactor

Một subscriber có thể xử lý từng item tuần tự và thêm độ trễ có chủ đích:

~~~java
Flux<PriceTick> consumeSlowly(
        RSocketRequester requester) {

    return requester
        .route("prices.watch")
        .retrieveFlux(PriceTick.class)
        .concatMap(tick ->
            processTick(tick)
                .then(Mono.delay(Duration.ofMillis(50)))
                .thenReturn(tick),
            1
        );
}
~~~

concatMap chỉ xử lý một inner publisher tại một thời điểm; tham số 1 là prefetch, giới hạn số item upstream được yêu cầu trước. Mono.delay thêm độ trễ mô phỏng cho mỗi item. Cần đo demand, queue và latency để xác nhận subscriber thật sự chậm hơn producer.

Không dùng Thread.sleep trên event-loop để tạo slow consumer. Cách đó block thread và có thể làm méo kết quả toàn hệ thống. Hãy dùng delay reactive hoặc workload xử lý CPU/I/O được kiểm soát.

## 7. Backpressure và buffer phải có giới hạn

Backpressure điều phối tốc độ phát theo nhu cầu downstream. Nhưng nếu producer không thể giảm tốc hoặc một đoạn pipeline chuyển sang queue, queue cần có giới hạn.

Ví dụ sink multicast có buffer hữu hạn:

~~~java
Sinks.Many<PriceTick> ticks =
    Sinks.many()
        .multicast()
        .onBackpressureBuffer(256, false);

Flux<PriceTick> stream = ticks.asFlux();

Sinks.EmitResult result = ticks.tryEmitNext(tick);

if (result != Sinks.EmitResult.OK) {
    handleEmitFailure(result, tick);
}
~~~

Với multicast có backpressure buffer, subscriber chậm có thể làm buffer đầy. Khi đó tryEmitNext có thể trả FAIL_OVERFLOW. Producer phải có policy rõ ràng thay vì bỏ qua kết quả.

Một số policy:

| Policy | Hành vi | Khi phù hợp |
|---|---|---|
| Bounded buffer | Giữ event trong giới hạn | Burst ngắn, cần giao đủ trong một khoảng |
| Drop latest | Bỏ event mới khi quá tải | Event mới không quan trọng bằng queue hiện có |
| Drop oldest | Bỏ event cũ, giữ trạng thái mới | Snapshot/state update |
| Coalesce | Gộp nhiều event thành một | Giá trị hiện tại, telemetry có thể tổng hợp |
| Reject | Trả lỗi quá tải cho producer/caller | Command cần phản hồi rõ |
| Persist | Ghi vào broker/store để phát lại | Event không được mất |

Không dùng unbounded queue để che giấu chênh lệch tốc độ. Nếu producer tạo 2.000 event/giây và consumer chỉ xử lý 1.000 event/giây, backlog tăng khoảng 1.000 event/giây. Buffer không giới hạn chỉ làm thời điểm hết bộ nhớ đến muộn hơn.

### Tính dung lượng buffer

\[
B \approx \lambda \times T \times S
\]

Trong đó:

- \(B\): dung lượng buffer theo byte.
- \(\lambda\): số event mỗi giây cần giữ.
- \(T\): thời gian chênh lệch tốc độ cần hấp thụ.
- \(S\): kích thước trung bình mỗi event tính cả overhead ước lượng.

Ví dụ 1.000 event/giây, giữ trong 10 giây, mỗi event chiếm trung bình 1 KB:

\[
B \approx 1000 \times 10 \times 1024
= 10{,}240{,}000 \text{ bytes}
\]

Đây chỉ là ước lượng payload. Object header, reference, queue node, DataBuffer/ByteBuf và metadata có thể làm bộ nhớ thực tế cao hơn. Hãy đo heap/direct memory trong test thay vì chỉ dựa vào phép tính.

## 8. Slow consumer theo từng loại sink

Các loại Reactor Sinks có semantics khác nhau. Bài test cần xác nhận chính sách được dùng đúng với yêu cầu dữ liệu.

| Sink | Khi subscriber chậm |
|---|---|
| multicast().onBackpressureBuffer() | Buffer theo demand chậm; có thể overflow khi giới hạn đầy |
| multicast().directBestEffort() | Subscriber không có demand có thể bỏ lỡ item; subscriber khác vẫn nhận |
| multicast().directAllOrNothing() | Nếu một subscriber thiếu demand, lần emit có thể thất bại cho tất cả |
| replay().limit(n) | Giữ lịch sử có giới hạn để subscriber mới nhận lại |
| unicast().onBackpressureBuffer() | Một subscriber duy nhất, queue đệm cho consumer |

Không so sánh throughput giữa các sink nếu semantics khác nhau. Một direct sink có thể có throughput cao vì bỏ event cho subscriber chậm; điều đó không có nghĩa nó xử lý cùng một yêu cầu giao nhận với sink buffer.

Trong test, ghi rõ:

- Event được phát bao nhiêu.
- Subscriber nhận bao nhiêu.
- Bao nhiêu event bị drop.
- Bao nhiêu lần emit thất bại.
- Buffer đạt đỉnh bao nhiêu.
- Subscriber nào chậm hoặc hủy.
- Event có được persist hoặc replay không.

## 9. Hủy stream và cleanup tài nguyên

Khi client chủ động hủy subscription, requester gửi tín hiệu cancel cho interaction. Nếu client mất mạng đột ngột, server chỉ phát hiện sau khi transport/KEEPALIVE/session timeout xử lý sự cố; với session có RESUME, state có thể còn được giữ trong thời gian chờ phục hồi. Sau khi interaction thực sự kết thúc, server phải giải phóng tài nguyên gắn với subscription đó.

Ví dụ theo dõi vòng đời một stream:

~~~java
@MessageMapping("prices.watch")
public Flux<PriceTick> watch() {
    return priceFeed.flux()
        .doOnSubscribe(subscription ->
            activeStreams.increment()
        )
        .doFinally(signalType -> {
            activeStreams.decrement();
            log.debug("Price stream ended: {}", signalType);
        });
}
~~~

doFinally được gọi khi stream complete, error hoặc cancel. Logic cleanup cần idempotent và không block event-loop.

Nếu handler đăng ký listener imperative vào một nguồn bên ngoài, phải hủy listener khi subscription kết thúc. Nếu không, client đã rời đi nhưng callback vẫn giữ reference tới subscriber và các object liên quan.

### Những tài nguyên cần kiểm tra sau cancel

- Active stream count trở về baseline.
- Listener/callback đã được deregister.
- Subscription và Disposable đã dispose.
- Queue theo client được giải phóng.
- Buffer không còn giữ payload của client đã rời.
- Connection pool không giữ requester/session đã đóng.
- Timer/retry task không còn chạy.
- Không có reference giữ session hoặc user context ngoài ý muốn.

Không chỉ đếm số stream mở. Hãy kiểm tra cả số stream đã cancel nhưng cleanup chưa hoàn tất.

## 10. Ngắt kết nối hàng loạt khác gì tải request cao?

Mass disconnect tạo ra một dạng tải khác. Khi nhiều client cùng mất mạng hoặc server đóng connection, hệ thống phải xử lý:

- Phát hiện connection mất.
- Hủy hoặc kết thúc các stream.
- Release socket, buffer, session và state.
- Tạo lại TCP/WebSocket connection.
- Thực hiện TLS handshake nếu dùng TLS.
- Gửi RSocket SETUP.
- RESUME session nếu được hỗ trợ.
- Khôi phục application subscription hoặc cursor.
- Tạo lại request đang chờ theo idempotency policy.

~~~mermaid
sequenceDiagram
    participant C as Many clients
    participant N as Network / Proxy
    participant S as RSocket server
    C->>N: Thousands of active connections
    N--xC: Network interruption
    Note over C,S: Connections close or time out
    C->>N: Reconnect attempts
    N->>S: TCP/TLS/WebSocket handshakes
    C->>S: SETUP or RESUME
    S-->>C: SETUP accepted / RESUME_OK
    C->>S: Re-subscribe / resume application work
~~~

Nếu 10.000 client reconnect trong cùng một giây, tải handshake có thể lớn hơn nhiều so với traffic ổn định. TLS, authentication, SETUP processing, discovery và subscription restoration đều có thể tạo burst.

Một bài test chỉ đóng client từ từ sẽ không phát hiện được reconnect storm. Cần thử nhiều mức tỷ lệ và nhiều kiểu phân bố thời gian.

## 11. Thiết kế mass-disconnect test

Có thể xây dựng các kịch bản:

| Kịch bản | Tỷ lệ/ngữ cảnh | Mục tiêu |
|---|---|---|
| Small churn | 1–5% client mỗi phút | Kiểm tra cleanup thường xuyên |
| Rolling disconnect | 10% client mỗi 30 giây | Kiểm tra phục hồi theo đợt |
| Large wave | 50% client trong 30 giây | Kiểm tra burst reconnect |
| Full outage | 100% client mất transport | Kiểm tra phục hồi toàn diện |
| Server instance loss | Một replica bị kill | Kiểm tra routing và reconnect |
| Proxy restart | WebSocket tunnel bị đóng | Kiểm tra client browser |
| Network partition | Client không thể tới server một thời gian | Kiểm tra timeout và retry |
| Repeated flap | Mất/kết nối lại nhiều lần | Kiểm tra resource leak và retry state |

Không bắt đầu bằng full outage nếu chưa biết giới hạn của môi trường test. Tăng dần tỷ lệ ngắt để xác định capacity và điểm suy giảm.

### Ngắt connection có kiểm soát

Có thể dùng test harness để chọn ngẫu nhiên một tập client, hủy RSocket requester hoặc đóng transport theo thời điểm đã định. Với kiểm thử network-level, dùng proxy/fault injection để reset hoặc drop connection. Mỗi phương pháp tạo ra hành vi khác nhau:

- Client dispose requester: mô phỏng ứng dụng chủ động đóng.
- Server close connection: mô phỏng deploy/drain hoặc server restart.
- TCP reset: mất kết nối đột ngột.
- Packet drop/partition: connection có thể treo cho tới khi timeout.
- Proxy idle close: kiểm tra tương tác với timeout của middlebox.

Ghi lại loại fault để không nhầm kết quả của graceful close với network partition.

## 12. Reconnect storm và backoff có jitter

Nếu mọi client dùng cùng một retry delay cố định, chúng có thể reconnect cùng thời điểm. Điều này tạo synchronized thundering herd.

Dùng exponential backoff có jitter:

\[
d_n = \min(d_{max}, d_0 \times 2^n) \times J
\]

Trong đó \(J\) là hệ số ngẫu nhiên trong khoảng được chọn, ví dụ 0,5 đến 1,5. Có thể dùng full jitter:

\[
d_n = random(0, \min(d_{max}, d_0 \times 2^n))
\]

Ví dụ Reactor retry:

~~~java
Retry reconnectPolicy =
    Retry.backoff(8, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(15))
        .jitter(0.5)
        .filter(this::isTransientConnectionFailure);
~~~

Đây là policy retry minh họa cho lỗi kết nối tạm thời. Trong production, cần quản lý reconnect ở một connection supervisor để tránh nhiều subscription độc lập cùng tạo retry loop cho một peer. Cần có deadline, giới hạn attempt, cancellation và trạng thái shutdown.

### Đo hiệu quả jitter

Trong mass-disconnect test, so sánh:

- Số reconnect attempt mỗi giây.
- Peak connection establishment rate.
- Peak TLS handshake rate.
- SETUP accepted/rejected rate.
- Thời gian tới khi 50%, 90%, 99% client trở lại.
- CPU và event-loop utilization của server trong recovery.
- Số retry bị từ chối hoặc timeout.

Một policy tốt không chỉ giúp mọi client cuối cùng kết nối lại; nó phân tán tải phục hồi để server không bị quá tải lần thứ hai.

## 13. Resume và reconnect trong bài test

Nếu RSocket resumption được bật, cần kiểm tra cả trường hợp resume thành công và resume bị từ chối.

Resume có thể giảm việc tạo lại interaction từ đầu, nhưng vẫn có chi phí:

- Transport mới phải được thiết lập.
- Server phải tìm session theo resume token.
- Resume state và frame buffer phải còn đủ.
- Frame bị thiếu có thể cần phát lại theo vị trí byte ngầm định của protocol. Vị trí này được tính từ độ dài frame đã mã hóa sau fragmentation, không tính frame-length field; nó không phải stream ID hoặc request count.
- Lease phải được cấp lại theo semantics của connection mới.
- Instance được chọn phải có resume state hoặc cơ chế chia sẻ state phù hợp.

Một bài test nên có hai nhóm:

| Nhóm | Hành vi | Kết quả |
|---|---|---|
| Resume-capable | Mất transport ngắn, state còn đủ | RESUME_OK, stream tiếp tục |
| Resume-rejected | Server restart hoặc state hết hạn | REJECTED_RESUME, application recovery |

Không mặc định RESUME_OK nghĩa là mọi dữ liệu nghiệp vụ đã được xử lý đúng một lần. Nếu command có side effect, vẫn cần idempotency. Resume phục hồi session/frame sequence theo protocol; nó không thay thế transaction hoặc deduplication nghiệp vụ.

## 14. Đo connection churn và resource cleanup

Khi connection mở/đóng liên tục, số socket và object liên quan có thể tạo áp lực đáng kể.

Theo dõi:

| Tài nguyên | Metric gợi ý |
|---|---|
| TCP socket | Established, time-wait, close/reset |
| WebSocket | Active, upgrade failure, close code |
| RSocket connection | Active, created, closed |
| Stream | Active, completed, errored, cancelled |
| Session/resume | Active session, resume success/rejection |
| JVM heap | Used, committed, allocation rate |
| Direct memory | Used/max nếu runtime expose |
| Netty ByteBuf | Allocation, release, leak detection |
| Event loop | Task queue, execution delay, busy time |
| Thread | Count, blocked, runnable |
| Connection pool | Active, idle, pending acquire |
| Retry scheduler | Active retry, scheduled task count |

### Heap và direct memory

Netty thường dùng pooled/direct ByteBuf cho I/O. Heap có thể ổn định trong khi direct memory tăng. Ngược lại, heap tăng có thể do queue, session state hoặc subscriber bị giữ reference.

Cần theo dõi cả:

- JVM heap used và old generation.
- GC count, pause time và allocation rate.
- Direct buffer pool.
- Container memory/RSS.
- Số lượng object/queue nếu có instrumentation.
- Native memory nếu ứng dụng dùng nhiều thành phần off-heap.

Không chỉ nhìn heap sau khi GC. Trong soak test, chụp xu hướng theo thời gian và so sánh cùng workload.

### Leak detection

Có thể bật Netty ResourceLeakDetector ở mức phù hợp cho test:

~~~java
ResourceLeakDetector.setLevel(
    ResourceLeakDetector.Level.PARANOID
);
~~~

PARANOID có overhead đáng kể, chỉ dùng trong bài kiểm thử chuyên biệt hoặc thời gian ngắn. Với soak test hiệu năng dài, có thể dùng mức thấp hơn và chạy một vòng riêng để tìm leak. Không bật chế độ tốn chi phí cao trong benchmark dùng để so sánh throughput.

## 15. Kiểm tra buffer, queue và memory slope

Một hệ thống ổn định thường có memory dao động theo tải nhưng không tăng vô hạn khi workload giữ nguyên.

~~~text
Memory
  ^
  |       /\/\/\/\/\   Stable with bounded variation
  |      /          \_/\/\
  |
  |  /--------------------  Unbounded growth
  | /
  +----------------------------------> Time
       Warm-up      Soak      Recovery
~~~

Các chỉ số cần quan sát:

- Buffer occupancy hiện tại và high-water mark.
- Số lần buffer overflow.
- Queue wait time.
- Số item pending.
- Kích thước payload trung bình/p95.
- Direct memory và heap slope.
- Số subscriber chậm.
- Số event bị drop hoặc persist.
- Thời gian buffer trở về baseline sau khi consumer nhanh lại.

Nếu không có metric buffer trực tiếp, có thể instrument ở lớp ứng dụng nơi queue được tạo. Không suy ra buffer size từ heap tổng vì heap chứa nhiều loại object khác.

## 16. Event-loop và thread starvation

RSocket Java thường dựa trên Reactor Netty/Netty. Event-loop xử lý I/O và callback. Nếu code blocking chạy trên event-loop, nhiều connection có thể bị ảnh hưởng cùng lúc.

Các dấu hiệu:

- Latency tăng dù CPU không cao.
- Nhiều connection cùng timeout.
- KEEPALIVE bị trễ.
- Event-loop task queue tăng.
- Thread dump cho thấy event-loop bị block bởi JDBC, file I/O hoặc Thread.sleep.
- Slow consumer làm operator queue tăng nhưng không phải CPU-bound.

Trong test, cố ý đưa một số handler có I/O chậm hoặc CPU nặng để xác nhận scheduler được dùng đúng. Không dùng block() hoặc synchronous I/O trên event-loop.

Nếu handler dùng JDBC blocking, chuyển sang boundedElastic hoặc dùng driver reactive. Với CPU-heavy work, cân nhắc scheduler dành cho tác vụ CPU và giới hạn concurrency.

## 17. Ví dụ server stream cho soak test

Một endpoint test có thể phát sequence có timestamp để client đo latency và phát hiện mất/lặp:

~~~java
public record LoadEvent(
    long sequence,
    Instant emittedAt,
    String partition
) {}

@Controller
public class LoadTestController {

    private final AtomicLong sequence = new AtomicLong();

    @MessageMapping("load.events")
    public Flux<LoadEvent> events() {
        return Flux.interval(Duration.ofMillis(10))
            .map(index ->
                new LoadEvent(
                    sequence.incrementAndGet(),
                    Instant.now(),
                    "partition-a"
                )
            );
    }
}
~~~

Đây là nguồn test đơn giản. Trong hệ thống thật, sequence nên có phạm vi rõ theo publisher/partition và không dùng một counter global gây contention cho workload lớn. Nếu nhiều client cùng subscribe, cần quyết định mỗi subscriber nhận cùng sequence hay mỗi subscription tạo luồng riêng.

Client ghi nhận latency và sequence:

~~~java
requester
    .route("load.events")
    .retrieveFlux(LoadEvent.class)
    .doOnNext(event -> {
        long latencyNanos =
            Duration.between(
                event.emittedAt(),
                Instant.now()
            ).toNanos();

        latencyRecorder.record(latencyNanos);
        sequenceTracker.accept(event.sequence());
    })
    .subscribe();
~~~

Ví dụ minh họa phép đo. Trong test thật, đồng hồ client và server cần đồng bộ nếu dùng timestamp tuyệt đối. Có thể dùng monotonic clock ở cùng process để đo local duration; nếu đo end-to-end qua nhiều máy, cần tính sai số clock hoặc dùng trace timestamp có đồng bộ.

Không tạo một subscription không được giữ/dispose. Load harness phải lưu Disposable và hủy khi kết thúc pha test.

## 18. Ví dụ client slow-consumer và disconnect

Một harness có thể chia nhóm client:

~~~java
Disposable fast = fastRequester
    .route("load.events")
    .retrieveFlux(LoadEvent.class)
    .subscribe(this::recordFastEvent, this::recordError);

Disposable slow = slowRequester
    .route("load.events")
    .retrieveFlux(LoadEvent.class)
    .concatMap(event ->
        processSlowly(event).thenReturn(event),
        1
    )
    .subscribe(this::recordSlowEvent, this::recordError);
~~~

Khi bắt đầu pha disconnect, hủy một phần subscription và dispose một phần requester theo lịch:

~~~java
slow.dispose();
slowRequester.dispose();
~~~

API đóng connection cụ thể phụ thuộc phiên bản Spring RSocketRequester đang dùng và cách requester được tạo/quản lý. Ví dụ dùng requester riêng cho mỗi nhóm để dispose slowRequester không đóng connection của fastRequester. Trong harness thực tế, mỗi virtual client cần sở hữu rõ requester/session của nó hoặc dùng pool có reference/lifecycle quản lý.

Sau khi dispose, xác nhận server thấy cancel/close và active stream/connection count giảm. Không giả định dispose là mô phỏng network partition; để kiểm tra mất mạng đột ngột, dùng fault injection ở transport/proxy.

## 19. Thiết kế tiêu chí pass/fail

Một test cần tiêu chí định lượng trước khi chạy. Ví dụ:

| Nhóm | Chỉ số | Tiêu chí mẫu |
|---|---|---|
| Throughput | Event/s hoặc request/s | Đạt ít nhất 95% mục tiêu |
| Latency | p95/p99 | Không vượt SLO đã định |
| Error | Transport/protocol/application error | Trong ngưỡng cho phép |
| Slow consumers | Buffer overflow/drop | Đúng policy, không vượt giới hạn |
| Memory | Heap/direct memory slope | Không tăng liên tục sau warm-up |
| GC | Pause p99 | Trong ngân sách latency |
| Stream cleanup | Active stream sau cancel | Trở về baseline |
| Reconnect | Client phục hồi | 99% trong recovery deadline |
| Setup | SETUP success rate | Đạt ngưỡng sau burst |
| Resume | Resume acceptance | Đúng tỷ lệ mong đợi khi state còn đủ |
| Resource | Socket/thread/event loop | Không tăng không giới hạn |
| Data correctness | Sequence/duplicate | Không mất/lặp ngoài semantics đã định |

Các con số trong bảng phải được thay bằng SLO và yêu cầu nghiệp vụ của hệ thống. Không dùng một ngưỡng phần trăm chung cho mọi ứng dụng.

### Định nghĩa recovery time

Có thể định nghĩa recovery time là thời gian từ lúc fault bắt đầu tới khi tất cả điều kiện ổn định được đáp ứng:

- Connection establishment rate trở về baseline.
- Error rate trở lại trong ngưỡng.
- Throughput đạt mức mục tiêu.
- p95/p99 latency trở lại SLO.
- Active stream và buffer không tiếp tục tăng.
- Client đã khôi phục subscription hoặc trạng thái nghiệp vụ cần thiết.

Đừng coi recovery hoàn tất chỉ vì socket đã mở lại.

## 20. Ma trận kịch bản kiểm thử

| Kịch bản | Cách tạo | Điều cần xác nhận |
|---|---|---|
| Soak 8 giờ | Tải ổn định theo profile | Memory/latency/throughput ổn định |
| Slow consumer 10% | Delay xử lý một nhóm client | Buffer và backpressure đúng policy |
| Very slow 2% | Giảm demand hoặc xử lý rất chậm | Overflow/drop/reject có kiểm soát |
| Consumer cancel | Hủy subscription ngẫu nhiên | Listener, stream và buffer được giải phóng |
| Disconnect 10% | Đóng connection theo đợt | Pool và server cleanup |
| Disconnect 50% | Fault injection trong 30 giây | Không tạo reconnect storm quá capacity |
| Full disconnect | Mất toàn bộ transport | Recovery có backoff/jitter |
| Resume success | Ngắt ngắn khi state còn đủ | RESUME_OK và stream tiếp tục |
| Resume rejected | Restart node hoặc hết state | Application recovery không duplicate |
| Repeated flap | Mất/kết nối lại nhiều vòng | Không leak session/socket/task |
| Payload lớn | Tăng payload size theo phân bố | Direct memory và network pressure |
| Long stream | Giữ stream nhiều giờ | Không tăng tài nguyên vô hạn |

Một test plan tốt lưu cả cấu hình workload và seed ngẫu nhiên. Khi phát hiện lỗi, có thể chạy lại cùng phân bố disconnect và tốc độ consumer.

## 21. Phân tích kết quả và tìm nguyên nhân

Không chỉ so sánh average latency. Average có thể che giấu một nhóm subscriber bị chậm nghiêm trọng.

Phân tích theo:

- p50, p90, p95, p99 và max latency.
- Throughput theo cửa sổ thời gian.
- Error rate theo transport/protocol/application.
- Buffer high-water mark và overflow.
- Memory slope trước/sau GC.
- Reconnect attempts per second.
- SETUP success latency.
- Resume success/rejection.
- Active stream và cancel rate.
- Server CPU, event-loop delay và dependency latency.

Một số mẫu chẩn đoán:

| Dấu hiệu | Khả năng | Kiểm tra tiếp |
|---|---|---|
| Heap/direct memory tăng dần | Queue/session/buffer leak | Heap dump, direct memory, subscriber cleanup |
| Throughput ổn nhưng p99 tăng | Queueing hoặc slow consumer | Demand, buffer wait, event loop |
| CPU tăng mạnh sau reconnect | TLS/SETUP/auth burst | Handshake rate, crypto, authentication |
| Active stream không giảm sau cancel | Cleanup thiếu | doFinally, listener dispose, subscription |
| Reconnect lặp lại | Health flapping hoặc timeout | Backoff, proxy idle, readiness |
| Resume rejection tăng sau deploy | Session state không sẵn ở node mới | Affinity, shared state, buffer lifetime |
| Overflow chỉ xuất hiện ở một nhóm | Consumer chậm hoặc policy không phù hợp | Consumer profile và queue bound |
| Server ổn nhưng generator quá tải | Load generator là bottleneck | Generator CPU/network/GC |

## 22. Báo cáo kết quả soak test

Một báo cáo cần cho người đọc hiểu cấu hình và điều kiện chạy, không chỉ đưa một con số throughput.

Mẫu báo cáo:

~~~text
Test: RSocket soak + slow consumer + mass disconnect
Build: <commit-or-version>
Transport: TCP / WebSocket
JDK / Spring / Reactor: <versions>
Server replicas: <count>
Client generators: <count>
Duration: <hours>
Target connections: <count>
Interaction mix: <percentages>
Payload profile: <sizes>
Slow consumers: <percentages>
Disconnect profile: <schedule>
Reconnect policy: <backoff/jitter>
Resume: enabled/disabled

Steady-state:
  throughput:
  p95 / p99 latency:
  error rate:
  active streams:
  heap/direct memory:
  buffer high-water mark:

Fault phase:
  disconnect rate:
  peak reconnect attempts/s:
  setup success rate:
  resume success/rejection:
  recovery time:

Final state:
  active connections:
  active streams:
  heap/direct memory:
  pending tasks:
  resource leaks:
  pass/fail:
~~~

Báo cáo cần lưu metric time series, log lỗi đại diện, cấu hình test và thời điểm bắt đầu/kết thúc mỗi pha. Không lưu token, credential hoặc payload nhạy cảm trong artifact test.

## 23. Những lỗi thường gặp khi viết bài test

| Cách làm | Vì sao không đủ | Cách cải thiện |
|---|---|---|
| Chạy test 5 phút rồi kết luận ổn định | Không thấy leak hoặc tích lũy | Soak nhiều giờ và đo slope |
| Chỉ dùng fast consumer | Không thấy queue/backpressure | Tạo nhiều nhóm tốc độ consumer |
| Dùng unbounded buffer | Che giấu producer-consumer mismatch | Buffer hữu hạn và policy rõ |
| Block event-loop để làm chậm client | Làm méo toàn hệ thống | Delay reactive hoặc xử lý có kiểm soát |
| Chỉ đóng client một cách graceful | Không mô phỏng partition/reset | Dùng fault injection |
| Reconnect tất cả ngay lập tức | Tạo tải không thực tế hoặc quá cực đoan | Thử nhiều profile, có/không jitter |
| Chỉ đo socket count | Bỏ qua interaction và stream | Đo active streams, throughput, latency |
| Chỉ đo heap | Bỏ qua direct/native memory | Đo heap, direct, RSS và container memory |
| Bỏ qua load generator | Generator có thể là bottleneck | Giám sát generator riêng |
| Dùng average latency | Che giấu tail latency | Theo dõi p95/p99 |
| Không kiểm tra dữ liệu sau reconnect | Có thể mất/lặp event | Sequence, event ID và idempotency |
| Chỉ test resume thành công | Không kiểm tra fallback | Test RESUME rejection và application recovery |

## 24. Quy trình chạy kiểm thử hiệu năng RSocket

1. Chọn profile workload và SLO dựa trên production.
2. Kiểm tra load generator đủ capacity.
3. Ghi baseline của connection, interaction, heap/direct memory và latency.
4. Warm-up rồi ramp lên tải mục tiêu.
5. Chạy steady soak đủ lâu.
6. Tăng dần tỷ lệ slow consumer và đo buffer/backpressure.
7. Hủy một phần stream để kiểm tra cleanup.
8. Ngắt connection theo nhiều profile từ nhỏ tới lớn.
9. Quan sát reconnect, SETUP, RESUME, TLS và connection churn.
10. Chạy recovery steady-state sau fault.
11. Drain toàn bộ client và xác nhận tài nguyên trở về baseline.
12. So sánh time series, log và SLO để xác định pass/fail.

Khi chạy lặp lại, giữ nguyên phiên bản ứng dụng, cấu hình JVM, payload, số generator và random seed nếu mục tiêu là so sánh build. Nếu thay đổi workload, ghi rõ để tránh so sánh sai.

## Ghi nhớ

- Soak test tìm lỗi tích lũy theo thời gian; load test ngắn không thay thế được.
- Slow consumer làm giảm demand và có thể khiến queue/buffer tăng.
- Buffer phải có giới hạn; overflow cần policy rõ như drop, reject, coalesce hoặc persist.
- Request-stream gắn với một interaction; REQUEST_N điều tiết response demand.
- Hủy subscription phải giải phóng listener, queue, buffer và state gắn với stream.
- Mass disconnect tạo tải handshake, TLS, SETUP, RESUME và subscription recovery.
- Exponential backoff có jitter giúp giảm reconnect storm.
- RESUME chỉ khôi phục session khi peer còn đủ state; fallback cần cursor/idempotency.
- Theo dõi heap và direct memory, GC, event loop, socket, active stream và queue.
- Đo p95/p99, throughput, error rate và recovery time, không chỉ average.
- Load generator cũng cần được giám sát để không trở thành bottleneck.
- Chỉ kết luận pass khi tải, dữ liệu và tài nguyên đều trở về trạng thái mong đợi sau fault.

## Tài liệu tham khảo

- [Project Reactor — Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/backpressure.html)
- [Project Reactor — Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html)
- [Project Reactor — Sinks API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.html)
- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Reactor Netty — Reference Guide](https://projectreactor.io/docs/netty/release/reference/index.html)
- [Netty — Reference-counted objects](https://netty.io/wiki/reference-counted-objects.html)
- [Micrometer — JVM metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)
- [OpenTelemetry — Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/)

