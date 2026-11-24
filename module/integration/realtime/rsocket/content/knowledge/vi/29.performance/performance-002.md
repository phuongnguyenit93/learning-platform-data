# Đo thông lượng và phân vị độ trễ thay vì chỉ thời gian trung bình

## Bối cảnh: một con số trung bình có thể che khuất trải nghiệm rất chậm

Một hệ thống RSocket có thể xử lý hàng nghìn request mỗi giây nhưng vẫn khiến một nhóm client phải chờ rất lâu. Phần lớn request có thể hoàn tất trong 20 ms, trong khi một số request phải chờ connection pool, event loop, database hoặc upstream service trong vài giây. Mean vẫn có thể trông tốt vì các request nhanh kéo giá trị xuống, dù người dùng vẫn gặp các lần chậm ở đuôi phân phối.

Để đánh giá hiệu năng, cần đo ít nhất hai nhóm chỉ số:

- **Thông lượng (throughput):** hệ thống hoàn thành được bao nhiêu công việc trong một đơn vị thời gian.
- **Phân vị độ trễ (latency percentile):** một tỷ lệ phần trăm request hoặc payload hoàn tất trong khoảng thời gian nào.

Đối với RSocket, cần phân biệt request/interaction với payload. Một request-stream có thể chỉ là một interaction nhưng phát ra hàng nghìn payload; request-channel có thể gửi và nhận nhiều payload ở cả hai hướng. Vì vậy, chỉ số request mỗi giây không thể thay thế payload mỗi giây hoặc byte mỗi giây.

Bài học này trình bày cách xác định đơn vị đo, tính throughput và goodput, đọc p50/p95/p99, thiết kế benchmark tránh sai lệch, thu thập histogram bằng Micrometer/Prometheus và phân tích kết quả trong điều kiện tải thực tế.

## 1. Xác định chính xác điều cần đo

Trước khi chạy benchmark, hãy mô tả một operation hoàn chỉnh. Ví dụ với route lấy trạng thái thiết bị:

1. Client gửi request-response.
2. Server giải mã payload và xác thực route.
3. Handler gọi service và database.
4. Server mã hóa response.
5. Client nhận và giải mã response.

Độ trễ end-to-end nên bao phủ khoảng thời gian mà caller thực sự chờ, từ lúc gửi request đến khi response sẵn sàng cho ứng dụng nếu đó là trải nghiệm cần đánh giá. Nếu chỉ đo thời gian trong service method, số liệu sẽ bỏ qua transport, queue, codec và xử lý phía client.

Với request-stream, một operation không có một thời điểm hoàn tất duy nhất. Nên đo riêng:

- Thời gian từ lúc gửi request đến payload đầu tiên (time to first item).
- Khoảng cách giữa các payload (inter-arrival time).
- Thời gian stream tồn tại đến complete/error/cancel.
- Số payload và số byte phát ra trong một giây.
- Độ trễ của từng event nếu nguồn có timestamp đáng tin cậy.

Với request-channel, cần đo thời gian từ lúc gửi payload đầu vào đến acknowledgement tương ứng, throughput của payload đầu vào và đầu ra, cùng thời gian hoàn tất toàn channel nếu nghiệp vụ có khái niệm hoàn tất.

### Chọn đơn vị đo theo interaction

| Interaction | Đơn vị throughput nên theo dõi | Độ trễ cần đo |
|---|---|---|
| Request-response | Request hoàn tất/giây | End-to-end latency mỗi request |
| Fire-and-forget | Message được gửi/giây và message được xử lý/giây nếu có ACK nghiệp vụ | Thời gian gửi; thời gian xử lý chỉ đo được khi có xác nhận riêng |
| Request-stream | Stream mở/giây, payload/giây, byte/giây | Time to first item, inter-arrival, stream duration |
| Request-channel | Channel mở/giây, payload vào/giây, payload ra/giây | Input-to-ack latency, channel duration |
| Kết nối | Connection mở/giây, active connection | Connect/SETUP latency, reconnect latency |

Không gộp tất cả các đơn vị vào một metric tên request throughput. Hãy đặt tên rõ để tránh so sánh nhầm giữa một request-response và một stream có 10.000 payload.

## 2. Tính throughput và goodput

Throughput là số operation hoàn tất trong khoảng thời gian đo:

\[
\text{throughput} =
\frac{\text{số operation hoàn tất}}{\text{thời gian đo}}
\]

Ví dụ, trong 60 giây có 120.000 request-response hoàn tất:

\[
\frac{120\,000}{60}=2\,000\ \text{request/giây}
\]

Tuy nhiên, hệ thống có thể hoàn tất nhiều request nhưng một tỷ lệ lớn trả lỗi. Vì vậy cần đo **goodput**: số operation thành công và có giá trị nghiệp vụ trong một giây.

\[
\text{goodput} =
\frac{\text{số operation thành công}}{\text{thời gian đo}}
\]

Ví dụ:

| Kết quả trong 60 giây | Số lượng |
|---|---:|
| Request đã gửi | 126.000 |
| Request kết thúc trong cửa sổ đo (success/error/timeout/cancel) | 120.000 |
| Thành công | 114.000 |
| Lỗi | 4.000 |
| Timeout hoặc bị hủy | 2.000 |
| Throughput hoàn tất | 2.000 request/s |
| Goodput | 1.900 request/s |
| Error rate trên request đã gửi | 3,17% |
| Tỷ lệ thất bại gồm error, timeout và cancel | 4,76% |

Throughput hoàn tất và goodput trả lời hai câu hỏi khác nhau. Khi so sánh hai phiên bản, không nên kết luận phiên bản có throughput cao hơn là tốt hơn nếu nó cũng trả nhiều lỗi hơn.

### Với stream, đếm cả interaction và payload

Một request-stream mở một interaction rồi phát nhiều payload. Nếu có 100 stream mỗi giây, mỗi stream phát trung bình 500 payload, payload throughput là 50.000 payload/giây. Hai con số này mô tả tải rất khác nhau.

Nên ghi nhận riêng:

- Interaction started/s và completed/s.
- Payload emitted/s và payload received/s.
- Bytes emitted/s và bytes received/s.
- Stream duration và số payload trung bình mỗi stream.
- Số stream bị cancel hoặc kết thúc do lỗi.

Với fire-and-forget, việc Mono<Void> hoàn tất phía client chỉ cho biết thao tác gửi ở phía client đã hoàn tất theo API. Nó không chứng minh handler server đã hoàn thành nghiệp vụ. Nếu cần goodput nghiệp vụ, phải có ACK, event log hoặc một chỉ số hoàn tất ở phía server.

## 3. Hiểu p50, p95 và p99

Phân vị pX là giá trị mà X phần trăm mẫu có độ trễ nhỏ hơn hoặc bằng. Ví dụ:

- **p50:** một nửa request hoàn tất trong thời gian này hoặc nhanh hơn; đây là median.
- **p95:** 95% request hoàn tất trong thời gian này hoặc nhanh hơn; 5% chậm hơn.
- **p99:** 99% request hoàn tất trong thời gian này hoặc nhanh hơn; 1% chậm hơn.

Giả sử một phép đo có kết quả:

| Chỉ số | Độ trễ |
|---|---:|
| Mean | 42 ms |
| p50 | 18 ms |
| p95 | 95 ms |
| p99 | 420 ms |
| Max | 2.800 ms |

Mean 42 ms không cho thấy 1% request chậm hơn 420 ms và request chậm nhất gần 3 giây. Với ứng dụng realtime, các đuôi phân phối này có thể làm dashboard, điều khiển thiết bị hoặc tương tác người dùng bị giật.

### Ví dụ phân phối có cùng mean nhưng tail khác nhau

Hai phiên bản có thể có mean gần bằng nhau nhưng p99 rất khác:

| Phiên bản | Mean | p50 | p95 | p99 |
|---|---:|---:|---:|---:|
| A | 40 ms | 35 ms | 60 ms | 90 ms |
| B | 40 ms | 20 ms | 75 ms | 600 ms |

Phiên bản B có nhiều request rất nhanh, nhưng một nhóm nhỏ phải chờ lâu. Chỉ nhìn mean sẽ bỏ lỡ khác biệt này.

p95 và p99 đặc biệt hữu ích khi hệ thống có queue, GC pause, pool contention, network retransmission hoặc một upstream thỉnh thoảng phản hồi chậm. Không nên chỉ theo dõi p99: hãy xem cả p50 để nhận biết mức nền và p95/p99 để nhận biết tail latency.

### Chọn phân vị theo mục tiêu dịch vụ

| Mục tiêu | Ví dụ chỉ số |
|---|---|
| Trải nghiệm phổ biến | p50 |
| Phần lớn request | p95 |
| Tail latency quan trọng | p99 |
| Phân tích sự cố hiếm | p99.9, max, trace mẫu |
| Độ ổn định toàn hệ thống | Phân vị theo route, node, interaction và cửa sổ thời gian |

Không có một phân vị duy nhất phù hợp cho mọi route. Route điều khiển thiết bị có thể cần p99 thấp; route xuất báo cáo dài có thể quan tâm throughput và thời gian hoàn tất hơn.

## 4. Vì sao mean không đủ và max cũng không đủ?

Mean tổng hợp tất cả mẫu thành một số. Một nhóm request rất chậm có thể bị che bởi số lượng lớn request nhanh. Max lại phản ánh đúng một mẫu chậm nhất nhưng rất nhạy với outlier, số lượng mẫu và thời gian quan sát.

Phân vị cung cấp thêm hình dạng của phân phối. Khi xem mean, p50, p95, p99 và max cùng nhau, có thể đặt câu hỏi chẩn đoán:

- Mean và p50 cùng tăng: phần lớn request chậm hơn, có thể do năng lực xử lý giảm.
- p50 ổn định nhưng p99 tăng: có thể xuất hiện queue, contention hoặc một dependency có tail xấu.
- p95 tăng đồng thời error rate tăng: có thể hệ thống đang tiến gần saturation.
- Max tăng đơn lẻ nhưng các phân vị khác ổn định: kiểm tra GC pause, retry hiếm hoặc outlier của môi trường.
- Throughput giảm trong khi latency tăng: dấu hiệu queue tăng hoặc tài nguyên đã bão hòa.

Không nên xóa mọi outlier khỏi dữ liệu chỉ để biểu đồ đẹp hơn. Một request mất 5 giây vẫn là trải nghiệm thật của một caller. Nếu cần loại bỏ lỗi do test harness, phải ghi rõ quy tắc loại trừ và báo cáo riêng số mẫu bị loại.

## 5. Đo đúng ranh giới thời gian

Với request-response, hãy đo từ thời điểm client bắt đầu gửi request đến khi response được nhận và decode xong ở tầng ứng dụng nếu đó là trải nghiệm caller cần đánh giá.

Ở mỗi tầng, có thể đặt timer riêng:

~~~mermaid
flowchart LR
    A["Client gửi request"] --> B["Transport và frame"]
    B --> C["Decode / route"]
    C --> D["Service và database"]
    D --> E["Encode response"]
    E --> F["Client nhận response"]
~~~

Các phép đo bổ sung giúp xác định nơi phát sinh latency:

- Client end-to-end latency: toàn bộ thời gian caller chờ.
- Server handler latency: thời gian xử lý trong handler và dependency được tính vào handler.
- Database latency: thời gian query.
- Serialization latency: encode/decode payload.
- Connect/SETUP latency: thời gian thiết lập connection.
- Queue wait: thời gian chờ trước khi công việc bắt đầu chạy.

Không cộng các percentile của từng tầng để suy ra percentile end-to-end. p99 của database cộng p99 của service không nhất thiết bằng p99 của request vì các phân phối và sự kiện chậm không xảy ra cùng mẫu. Hãy đo trực tiếp end-to-end; timer theo tầng dùng để điều tra.

### Dùng đồng hồ monotonic cho thời lượng

Trong cùng một process, đo thời lượng bằng System.nanoTime(), không dùng System.currentTimeMillis(). Đồng hồ monotonic không bị nhảy khi đồng hồ hệ thống được đồng bộ hoặc điều chỉnh.

~~~java
long started = System.nanoTime();

return service.findStatus(deviceId)
    .doFinally(signal -> {
        long elapsedNanos = System.nanoTime() - started;
        latencyTimer.record(elapsedNanos, TimeUnit.NANOSECONDS);
    });
~~~

Ví dụ này đo thời gian subscription tới terminal signal. Nếu publisher được tạo trước nhưng subscribe sau, hãy đặt thời điểm bắt đầu bên trong Flux.defer hoặc Mono.defer để mỗi subscription có mốc riêng.

Không dùng nanoTime ở hai máy khác nhau để tính one-way latency vì giá trị không cùng clock domain. Nếu cần đo thời gian từ server phát event tới client nhận event, cần đồng bộ clock đủ chính xác hoặc dùng tracing/measurement design phù hợp. Với request-response, đo round-trip tại client thường đơn giản và đáng tin cậy hơn.

## 6. Đo request-stream đúng cách

Một stream có thể sống vài mili giây hoặc vài giờ. Chỉ ghi một timer từ lúc mở stream đến lúc complete sẽ không mô tả độ trễ của từng payload.

Nên tách ít nhất ba chỉ số:

1. **Time to first item:** từ lúc client gửi request đến payload đầu tiên.
2. **Inter-arrival latency:** khoảng thời gian giữa hai payload liên tiếp hoặc độ trễ từ event source tới client.
3. **Stream lifetime:** từ lúc bắt đầu subscription đến complete, error hoặc cancel.

Ví dụ đo time to first item và stream lifetime ở client:

~~~java
Flux<ReadingEvent> measuredStream(RSocketRequester requester,
                                  SensorQuery query) {
    return Flux.defer(() -> {
        long started = System.nanoTime();
        AtomicBoolean firstItem = new AtomicBoolean();

        return requester.route("sensor.readings")
            .data(query)
            .retrieveFlux(ReadingEvent.class)
            .doOnNext(event -> {
                if (firstItem.compareAndSet(false, true)) {
                    long firstLatency = System.nanoTime() - started;
                    firstItemTimer.record(
                        firstLatency,
                        TimeUnit.NANOSECONDS
                    );
                }
                payloadReceivedCounter.increment();
            })
            .doFinally(signal -> {
                long lifetime = System.nanoTime() - started;
                streamLifetimeTimer.record(
                    lifetime,
                    TimeUnit.NANOSECONDS
                );
            });
    });
}
~~~

Đây là ví dụ minh họa; timer và counter cần được inject từ MeterRegistry. Nếu stream không phát phần tử nào, time-to-first-item không có mẫu; cần ghi riêng stream-empty hoặc first-item-timeout để không làm metric biến mất khỏi phân tích.

Inter-arrival time có thể được đo bằng cách giữ mốc nanoTime của payload trước đó. Nhưng inter-arrival thấp không đồng nghĩa event source latency thấp: server có thể phát dồn các event cũ sau một khoảng tắc nghẽn. Nếu cần event freshness, hãy mang event timestamp hoặc sequence trong payload và đo độ trễ nguồn tới consumer bằng clock đồng bộ hoặc watermark.

## 7. Thiết kế workload: open-loop và closed-loop

Cách tạo tải ảnh hưởng trực tiếp tới kết quả đo.

### Closed-loop load

Trong mô hình closed-loop, mỗi virtual user gửi request mới sau khi request trước hoàn tất. Nếu latency tăng, tốc độ gửi tự giảm.

Ví dụ: mỗi client chỉ giữ một request đang chạy. Khi server chậm từ 20 ms lên 200 ms, client gửi ít request hơn. Điều này mô tả một client chờ response rồi mới tiếp tục, nhưng có thể che giấu queueing khi hệ thống quá tải.

### Open-loop load

Trong mô hình open-loop, load generator phát request theo lịch hoặc tốc độ mục tiêu độc lập với thời gian response trước đó. Nếu server chậm, request vẫn tiếp tục đến theo tốc độ đã định, làm lộ queue và tail latency.

Ví dụ: gửi 1.000 request/giây trong suốt thời gian đo. Nếu server chỉ hoàn tất 700 request/giây, backlog sẽ tăng hoặc hệ thống bắt đầu từ chối/timeout. Kết quả cho thấy năng lực không đáp ứng offered load.

~~~mermaid
flowchart TD
    A["Load generator"] --> B{"Mô hình tải"}
    B --> C["Closed-loop"]
    B --> D["Open-loop"]
    C --> E["Chờ response rồi gửi tiếp"]
    D --> F["Gửi theo lịch độc lập response"]
    E --> G["Có thể tự giảm offered load khi server chậm"]
    F --> H["Lộ queueing và tail latency khi quá tải"]
~~~

Không có mô hình nào luôn đúng. Closed-loop phù hợp khi người dùng thực sự chờ kết quả trước hành động tiếp theo. Open-loop phù hợp để kiểm tra hệ thống có chịu được tốc độ sự kiện đến cố định hay không. Nên thử cả hai khi workload production có cả hai kiểu.

### Coordinated omission

Coordinated omission xảy ra khi load generator ngừng tạo mẫu trong lúc hệ thống đang chậm, rồi chỉ đo những request được gửi sau khi response trước hoàn tất. Khoảng thời gian hệ thống bị nghẽn không được phản ánh đầy đủ trong histogram.

Để hạn chế sai lệch:

- Dùng lịch phát request độc lập với response khi mô phỏng arrival rate cố định.
- Ghi nhận thời điểm request dự kiến được phát và thời điểm thực tế được gửi.
- Dùng load generator có khả năng ghi latency đã hiệu chỉnh theo khoảng thời gian bị bỏ qua nếu phù hợp.
- Báo cáo offered rate, achieved rate và số request đang chờ cùng nhau.

Nếu dùng closed-loop, hãy mô tả rõ mô hình và không so sánh trực tiếp với kết quả open-loop như thể chúng đo cùng một workload.

## 8. Dùng Little's Law để hiểu concurrency và queue

Trong một hệ thống ổn định, Little's Law liên hệ số công việc trung bình đang nằm trong hệ thống, throughput và thời gian lưu lại:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số operation trung bình đang in-flight trong hệ thống.
- \(\lambda\): throughput trung bình, operation/giây.
- \(W\): thời gian trung bình một operation ở trong hệ thống, tính bằng giây.

Ví dụ hệ thống hoàn tất trung bình 2.000 request/giây và latency trung bình là 50 ms:

\[
L = 2\,000 \times 0.05 = 100
\]

Trung bình có khoảng 100 request đang in-flight. Nếu latency trung bình tăng lên 200 ms mà throughput vẫn 2.000 request/giây, số request in-flight trung bình tăng lên khoảng 400.

Đây là quan hệ ở trạng thái ổn định và dùng mean, không thay p95 hoặc p99 vào W. Khi backlog tăng liên tục, hệ thống chưa ở trạng thái ổn định; hãy đo queue depth và tốc độ đến/hoàn tất để thấy sự mất cân bằng.

Little's Law giúp đặt concurrency hợp lý. Tăng số client hoặc số stream không tự làm throughput tăng nếu database, CPU hoặc network đã bão hòa. Nó có thể chỉ làm queue và tail latency lớn hơn.

## 9. Đo bằng Micrometer Timer và histogram

Micrometer Timer phù hợp để ghi nhận thời lượng và số lần hoàn tất. Timer có thể xuất count, total time, max và histogram tùy registry/cấu hình.

Ví dụ tạo timer cho route request-response:

~~~java
Timer requestTimer = Timer.builder("rsocket.request.latency")
    .description("End-to-end RSocket request latency")
    .tag("route", "sensor.status")
    .tag("interaction", "request-response")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(10),
        Duration.ofMillis(25),
        Duration.ofMillis(50),
        Duration.ofMillis(100),
        Duration.ofMillis(250),
        Duration.ofMillis(500),
        Duration.ofSeconds(1)
    )
    .register(meterRegistry);
~~~

publishPercentileHistogram() yêu cầu Micrometer xuất bucket histogram khi registry hỗ trợ. serviceLevelObjectives(...) bổ sung các ngưỡng bucket gắn với mục tiêu dịch vụ. Các ngưỡng nên bao phủ vùng latency cần phân tích; không nên tạo quá nhiều bucket tùy tiện vì mỗi tag/bucket làm tăng cardinality và chi phí lưu trữ.

Đo publisher theo vòng đời:

~~~java
Mono<DeviceStatus> measuredStatus(String deviceId) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(meterRegistry);

        return deviceService.findStatus(deviceId)
            .doFinally(signal -> sample.stop(
                timerForOutcome(signal)
            ));
    });
}

private Timer timerForOutcome(SignalType signal) {
    String outcome =
        signal == SignalType.ON_ERROR ? "error" :
        signal == SignalType.CANCEL ? "cancelled" :
        "completed";

    return Timer.builder("rsocket.request.latency")
        .tag("route", "sensor.status")
        .tag("interaction", "request-response")
        .tag("outcome", outcome)
        .publishPercentileHistogram()
        .register(meterRegistry);
}
~~~

Trong ứng dụng thực tế, nên tạo và cache Timer theo tập tag hữu hạn thay vì xây builder ở mỗi request. Ví dụ này minh họa việc ghi nhận cả complete, error và cancel. Đặt Timer.Sample bên trong defer để mỗi subscription có thời điểm bắt đầu riêng.

### Client latency và server latency là hai metric khác nhau

Nếu muốn đo trải nghiệm caller, timer nên bao quanh requester ở phía client. Nếu muốn biết handler mất bao lâu, timer ở server. Không đặt tên cả hai là cùng một latency metric.

Ví dụ naming:

| Metric | Vị trí | Ý nghĩa |
|---|---|---|
| rsocket.client.request.latency | Client | Thời gian caller chờ response |
| rsocket.server.handler.latency | Server | Thời gian xử lý handler |
| rsocket.connection.setup.latency | Client/server | Thời gian thiết lập connection |
| rsocket.stream.time.to.first | Client | Thời gian đến payload đầu tiên |
| rsocket.stream.lifetime | Client/server | Tuổi thọ interaction |
| rsocket.payload.received | Client | Số payload nhận được |
| rsocket.payload.bytes | Client/server | Số byte truyền |

Đừng đặt tag là deviceId, userId, requestId hoặc eventId trên Timer histogram nếu các giá trị này có thể rất nhiều. Tag có cardinality cao có thể làm Prometheus hoặc metrics backend phình số time series. Dùng log hoặc trace để tìm từng request; metrics nên dùng tag hữu hạn như route template, interaction, outcome và region.

## 10. Đọc percentile từ Prometheus histogram

Khi dùng Micrometer Prometheus registry với histogram bucket, có thể tính p99 trên nhiều instance bằng cách cộng bucket trước khi tính quantile.

Ví dụ metric Timer tên rsocket.request.latency được export thành histogram:

~~~promql
histogram_quantile(
  0.99,
  sum by (le, route) (
    rate(rsocket_request_latency_seconds_bucket[5m])
  )
)
~~~

Tương tự, p95:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(rsocket_request_latency_seconds_bucket[5m])
  )
)
~~~

Throughput hoàn tất có thể ước lượng từ rate của count:

~~~promql
sum by (route) (
  rate(rsocket_request_latency_seconds_count[1m])
)
~~~

Tên metric thực tế phụ thuộc tên Timer, registry và quy tắc đặt tên. Hãy kiểm tra endpoint metrics của ứng dụng trước khi dùng query trong dashboard.

### Không lấy trung bình p99 của từng instance

Giả sử Node A có p99 là 50 ms và Node B có p99 là 500 ms. Trung bình hai p99 thành 275 ms không phải p99 của toàn cluster.

Percentile không phải đại lượng cộng được. Để tính quantile tổng hợp, cần cộng histogram bucket tương ứng rồi mới áp dụng histogram_quantile. Nếu chỉ có client-side percentile đã tính riêng trên từng instance, không thể ghép chúng thành percentile toàn hệ thống một cách chính xác.

### Histogram bucket ảnh hưởng độ chính xác

Histogram lượng tử hóa độ trễ vào các bucket. Nếu bucket quá rộng quanh vùng p99, kết quả quantile sẽ kém chính xác. Hãy đặt bucket dày hơn ở vùng quan trọng của SLO và theo dõi số mẫu trong mỗi cửa sổ.

Client-side percentile của Micrometer có thể hữu ích cho từng process nhưng thường không thể tổng hợp chính xác giữa các instance. Histogram bucket phù hợp hơn khi cần aggregate qua Prometheus.

## 11. Số lượng mẫu và cửa sổ thời gian

Percentile ở đuôi cần đủ mẫu. Nếu chỉ có 100 request, p99 gần như phụ thuộc vào một mẫu cao nhất; nó không phải ước lượng ổn định. Với 10.000 mẫu, 1% tail tương ứng khoảng 100 mẫu, nhưng độ ổn định vẫn phụ thuộc phân phối và cách lấy mẫu.

Hãy cân nhắc:

- Thu thập đủ request cho từng route và từng interaction.
- Dùng cửa sổ thời gian phù hợp với traffic, ví dụ 1-5 phút cho dashboard vận hành và cửa sổ dài hơn cho benchmark.
- Không gộp một giờ traffic thấp với một phút spike nếu mục tiêu là phân tích spike.
- Hiển thị số mẫu cùng percentile để người đọc biết độ tin cậy.
- Lặp benchmark nhiều lần và báo cáo độ dao động giữa các lần chạy.

Với p99.9, cần lượng mẫu lớn hơn đáng kể để có đủ quan sát ở tail. Không nên báo cáo p99.9 với vài trăm request rồi xem đó là kết quả chắc chắn.

Percentile trên cửa sổ ngắn có thể nhảy mạnh khi traffic ít. Có thể dùng histogram dài hơn hoặc bổ sung trace mẫu để chẩn đoán, nhưng phải ghi rõ cửa sổ và số lượng request.

## 12. Quy trình benchmark RSocket có thể lặp lại

Một benchmark có ý nghĩa cần cố định các yếu tố ảnh hưởng. Quy trình gợi ý:

### Bước 1: định nghĩa workload

Ghi rõ:

- Interaction model: request-response, request-stream, request-channel hay fire-and-forget.
- Route và logic nghiệp vụ được đo.
- Kích thước payload và metadata.
- Tỷ lệ thành công/lỗi dự kiến.
- Số connection, số stream đồng thời và offered rate.
- Thời gian chạy, warm-up và thời gian nghỉ.
- Transport TCP hay WebSocket, TLS có bật hay không.

### Bước 2: tách setup khỏi steady-state

Đo riêng connection setup nếu đó là mục tiêu. Với benchmark throughput steady-state, tạo connection trước, chờ sẵn sàng rồi mới bắt đầu cửa sổ đo. Nếu mỗi operation mở một connection mới trong khi production tái sử dụng connection, kết quả sẽ không phản ánh workload thật.

### Bước 3: warm-up JVM

JVM cần thời gian để class loading, JIT compilation, profile và tối ưu code. Chạy warm-up trước khi lấy số liệu. Không lấy vài giây đầu làm kết quả steady-state.

### Bước 4: tăng tải theo từng mức

Ví dụ chạy 100, 250, 500, 1.000, 1.500 và 2.000 request/giây. Ở mỗi mức, giữ đủ lâu để quan sát throughput, latency distribution, error và tài nguyên. Không nhảy thẳng tới tải cực đại nếu chưa biết điểm saturation.

### Bước 5: đo trong cửa sổ ổn định

Ghi offered rate, completed rate, goodput, p50/p95/p99, error/timeout, active connection, active stream, CPU, heap, GC và queue depth. Nếu throughput vẫn tăng trong khi p99 tăng đột biến, hệ thống có thể đang tiến gần điểm bão hòa.

### Bước 6: lặp lại và ghi môi trường

Ghi phiên bản JDK, Spring, Reactor, RSocket, Netty, cấu hình heap, CPU, memory, OS, kernel, transport, TLS, network path và cấu hình database/broker. Chạy nhiều lần trong điều kiện tương đương để phân biệt thay đổi thực với nhiễu môi trường.

## 13. JMH và load test end-to-end dùng cho mục đích khác nhau

JMH phù hợp đo các đoạn code nhỏ trong JVM như:

- Encode/decode DTO.
- Chuyển đổi payload.
- Tạo metadata hoặc route.
- Áp dụng operator trên publisher trong phạm vi benchmark cô lập.
- So sánh cấu trúc dữ liệu hoặc thuật toán.

JMH không tự thay thế một load test RSocket qua mạng. Nếu benchmark cần đo TCP/WebSocket, connection multiplexing, backpressure, network latency, server queue và nhiều client đồng thời, cần một load generator end-to-end có thể mở connection và phát đúng interaction.

| Công cụ/phương pháp | Dùng để đo | Không nên dùng để kết luận |
|---|---|---|
| JMH | Chi phí CPU/memory của đoạn code trong JVM | Capacity của cluster RSocket qua mạng |
| Unit benchmark | Mapping, codec, operator nhỏ | Tail latency production |
| RSocket integration test | Độ đúng của interaction và lifecycle | Throughput cực đại |
| End-to-end load test | Throughput, latency, saturation trên hệ thống thật | Micro-cost của một method |
| Production metrics/tracing | Hành vi workload thực | So sánh công bằng nếu môi trường thay đổi |

Nếu codec là nút thắt, dùng JMH để cô lập chi phí encode/decode rồi dùng load test để xác nhận tác động end-to-end. Không ngoại suy tỷ lệ tăng tốc từ microbenchmark thành tỷ lệ tăng throughput của toàn hệ thống.

## 14. Tránh để load generator trở thành nút thắt

Load generator cũng tiêu thụ CPU, heap, network và event loop. Nếu máy phát tải bão hòa trước server, throughput đo được là giới hạn của generator.

Kiểm tra:

- CPU và GC của load generator.
- Số connection và socket giới hạn.
- Network interface và bandwidth.
- Số event loop/thread.
- Khả năng phát request đúng offered rate.
- Queue nội bộ của generator.
- Độ trễ từ thời điểm dự kiến phát đến thời điểm thực sự gửi.

Có thể chạy nhiều load generator trên các máy riêng để tăng offered load. Dùng cùng cấu hình và phân chia tải rõ ràng; tránh để các máy phát tải cùng tranh một CPU hoặc network interface yếu.

Nếu đo one-way latency giữa nhiều host, cần clock synchronization và biết sai số đồng hồ. Với round-trip latency, đo tại client bằng monotonic clock để tránh phụ thuộc đồng bộ đồng hồ giữa hai máy.

## 15. Theo dõi saturation và nguyên nhân tail latency

Khi throughput không tăng dù offered load tăng, hệ thống có thể đã đạt saturation. Dấu hiệu thường gặp:

- CPU gần 100% hoặc một event loop thread bị nóng.
- Heap tăng, GC pause dài hoặc allocation rate cao.
- Database connection pool cạn.
- Pending acquire hoặc queue depth tăng.
- Netty event loop bị block.
- Upstream WebClient hoặc broker chậm.
- Network bandwidth hoặc packet retransmission tăng.
- Active stream tăng nhưng payload consumption giảm.
- Timeout, cancellation và reconnect tăng.

Cần xem latency percentile cùng metrics tài nguyên. Một p99 tăng không tự chỉ ra nguyên nhân; nó là tín hiệu để drill down theo route, node, dependency và trace.

### Không tối ưu throughput bằng cách bỏ qua tail

Ví dụ tăng prefetch hoặc buffer có thể làm throughput ngắn hạn tăng, nhưng cũng có thể làm queue sâu và p99 xấu hơn. Tăng concurrency có thể giữ CPU bận hơn nhưng kéo dài thời gian chờ database. Tối ưu cần đánh giá cả throughput, goodput, latency và error.

Một điểm vận hành tốt thường nằm trước vùng saturation: throughput đạt gần mức mục tiêu nhưng queue vẫn ổn định, p95/p99 trong giới hạn và hệ thống còn capacity cho burst.

## 16. Xây dựng bảng báo cáo benchmark

Một báo cáo tối thiểu nên có dạng:

| Offered rate | Completed/s | Goodput/s | p50 | p95 | p99 | Error rate | CPU |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 250/s | 250 | 249 | 12 ms | 20 ms | 35 ms | 0,1% | 22% |
| 500/s | 500 | 498 | 14 ms | 28 ms | 55 ms | 0,2% | 35% |
| 1.000/s | 998 | 990 | 18 ms | 45 ms | 110 ms | 0,8% | 58% |
| 1.500/s | 1.420 | 1.380 | 35 ms | 180 ms | 620 ms | 2,8% | 82% |
| 2.000/s | 1.510 | 1.420 | 90 ms | 520 ms | 1.900 ms | 6,0% | 96% |

Các con số trên chỉ minh họa cách trình bày, không phải kết quả benchmark RSocket thực tế.

Bảng cho thấy ở 1.500-2.000 offered request/s, completed throughput không tăng tương ứng, trong khi p95/p99 và error rate tăng nhanh. Điểm này có thể là vùng saturation. Chỉ nhìn throughput tối đa sẽ dễ chọn mức tải không ổn định.

Một báo cáo tốt còn có:

- Số mẫu và thời lượng cửa sổ.
- Payload size và interaction model.
- Connection/stream concurrency.
- Transport và TLS.
- JVM, CPU, memory và GC.
- Node có lỗi hoặc outlier.
- Offered rate và achieved rate.
- Histogram hoặc biểu đồ latency distribution.
- Ghi chú về warm-up và lần chạy.

## 17. Những lỗi đo lường thường gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ báo cáo mean | Che khuất tail latency | Báo cáo p50, p95, p99 và max |
| Chỉ đếm request/giây cho stream | Không biết số payload thực tế | Đo interaction, payload và byte riêng |
| Chỉ đo server handler | Bỏ qua network, queue và codec phía client | Đo end-to-end ở client cùng metric theo tầng |
| Dùng currentTimeMillis cho duration | Bị ảnh hưởng khi clock hệ thống điều chỉnh | Dùng System.nanoTime |
| Dùng closed-loop cho arrival rate cố định | Offered load tự giảm khi server chậm | Dùng open-loop hoặc báo rõ load model |
| Bỏ qua coordinated omission | Histogram đánh giá thấp khoảng nghẽn | Ghi lịch phát và dùng load generator phù hợp |
| Lấy trung bình p99 của các node | Quantile tổng hợp sai | Aggregate histogram bucket rồi tính quantile |
| Đo quá ít mẫu cho p99 | Tail estimate không ổn định | Tăng số mẫu và báo sample count |
| Warm-up không đủ | Kết quả bị ảnh hưởng bởi JIT/class loading | Warm-up trước cửa sổ đo |
| Mở connection cho mọi request | Benchmark không giống production reuse | Đo setup riêng và reuse connection khi phù hợp |
| Load generator bị bão hòa | Đánh giá thấp năng lực server | Theo dõi generator và phân tán tải |
| Bỏ request lỗi khỏi báo cáo | Goodput bị hiểu nhầm là throughput | Báo lỗi, timeout và cancel riêng |
| Gắn tag metric bằng userId/eventId | Cardinality tăng mạnh | Dùng tag hữu hạn; trace/log cho từng request |
| Cộng percentile từng tầng | Suy ra end-to-end sai | Đo end-to-end trực tiếp |
| Chỉ tối ưu throughput | p99 hoặc error rate có thể xấu đi | Đánh giá throughput, goodput, latency và saturation cùng lúc |

## Kết luận

Thông lượng cho biết hệ thống hoàn thành bao nhiêu công việc trong một giây; phân vị độ trễ cho biết phần lớn và nhóm request chậm nhất phải chờ bao lâu. Mean hữu ích để mô tả xu hướng tổng thể nhưng không đủ để đánh giá trải nghiệm realtime. Hãy theo dõi p50, p95, p99 cùng error rate, timeout, throughput và goodput.

Với RSocket, đo riêng interaction, payload, byte và vòng đời stream. Dùng timer end-to-end ở client, timer theo tầng để điều tra, histogram để tổng hợp percentile qua nhiều node và load model phù hợp với workload. Warm-up JVM, tránh coordinated omission, kiểm tra load generator và ghi lại môi trường benchmark. Khi throughput chững lại trong khi p95/p99 tăng, hãy tìm điểm saturation thay vì chỉ tăng concurrency hoặc buffer.

## Tài liệu tham khảo

- [Micrometer — Timers và Distribution Statistics](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer — Histograms và Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Prometheus — Histograms and summaries](https://prometheus.io/docs/practices/histograms/)
- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh)
- [HdrHistogram — High Dynamic Range Histogram](https://github.com/HdrHistogram/HdrHistogram)
- [Project Reactor — Metrics và instrumentation](https://projectreactor.io/docs/core/release/reference/)
- [RSocket Protocol](https://rsocket.io/about/protocol/)
