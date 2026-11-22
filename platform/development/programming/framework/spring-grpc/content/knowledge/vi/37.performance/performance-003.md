# Unary latency và throughput

Unary RPC gửi một request và nhận một response trong một lần gọi. Khi đánh giá hiệu năng Spring gRPC, hai chỉ số quan trọng nhất là **latency** — thời gian hoàn thành một RPC — và **throughput** — số RPC hoàn thành trong một đơn vị thời gian. Hai chỉ số liên quan nhưng không thể thay thế nhau: một hệ thống có thể trả lời rất nhanh khi ít tải nhưng nhanh chóng bão hòa khi có nhiều client; một hệ thống có throughput cao cũng có thể tạo tail latency rất lớn.

Để đo đúng, cần phân biệt thời gian ở client, thời gian xử lý tại server, số request được gửi, số request hoàn thành thành công và số request lỗi. Bài này tập trung vào unary RPC, cách thiết kế phép đo có tải, xác định điểm bão hòa và tối ưu dựa trên số liệu.

## 1. Định nghĩa latency và throughput

**End-to-end latency** của unary RPC là khoảng thời gian từ lúc client bắt đầu gửi call đến khi nhận được response hoặc lỗi cuối cùng. Nó có thể bao gồm:

- Thời gian chờ ở client trước khi call được gửi.
- Client-side interceptor, credential và serialization.
- HTTP/2 scheduling, network và TLS transport.
- Server-side queueing, deserialization và interceptor.
- Business handler cùng các dependency như database hoặc cache.
- Server serialization, response transport và client deserialization.

Không phải phép đo nào cũng bao gồm tất cả các thành phần. Ví dụ timer đặt bên trong handler chỉ đo một phần server processing; timer quanh lời gọi stub đo gần với trải nghiệm client hơn. Khi báo cáo, phải ghi rõ điểm bắt đầu và kết thúc.

**Throughput** thường được báo bằng RPC hoàn thành mỗi giây. Cần tách:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Offered rate | Tốc độ load generator cố gắng gửi request |
| Started RPC/s | Số RPC thực sự bắt đầu mỗi giây |
| Completed RPC/s | Tổng RPC kết thúc mỗi giây, gồm cả thành công và lỗi |
| Successful throughput / goodput | Số RPC hoàn thành thành công mỗi giây |
| Error rate | Tỷ lệ RPC kết thúc bằng status lỗi hoặc timeout |

Không báo throughput chỉ bằng số request đã gửi. Nếu client phát 2.000 RPC/s nhưng server chỉ hoàn thành 1.200 RPC/s và phần còn lại timeout, goodput là 1.200 RPC/s, không phải 2.000 RPC/s.

## 2. Đọc latency percentiles

Latency trung bình hữu ích để theo dõi xu hướng, nhưng thường che giấu trải nghiệm của nhóm request chậm. Hãy báo percentile:

| Chỉ số | Cách hiểu |
| --- | --- |
| p50 | Một nửa RPC hoàn thành không chậm hơn giá trị này |
| p90 | 90% RPC hoàn thành không chậm hơn giá trị này |
| p95 | 95% RPC hoàn thành không chậm hơn giá trị này |
| p99 | 99% RPC hoàn thành không chậm hơn giá trị này |
| p99.9 | Theo dõi phần đuôi rất chậm khi volume đủ lớn |

Ví dụ p50 = 18 ms nhưng p99 = 420 ms cho thấy phần lớn request nhanh, song một nhóm nhỏ bị chậm đáng kể. Chỉ báo cáo average có thể làm vấn đề này biến mất.

Latency histogram nên dùng bucket phù hợp với SLA, giữ cùng đơn vị và cùng ranh giới đo giữa các lần benchmark. Không lấy trung bình các percentile từ nhiều instance để tạo percentile toàn hệ thống; hãy merge histogram hoặc tính percentile từ tập quan sát phù hợp. Với lượng mẫu nhỏ, p99/p99.9 không ổn định và dễ gây kết luận sai.

Theo dõi thêm:

- RPC count và goodput theo service/method.
- Status code, timeout và cancellation.
- Payload size và concurrency.
- Client queue time, server queue time nếu đo được.
- CPU, heap, allocation rate, GC pause và thread pool saturation.
- Network bytes, retransmission và connection state.

## 3. Latency của unary RPC hình thành ở đâu?

Luồng cơ bản:

```text
Client creates request
       |
       v
Client interceptor + serialization
       |
       v
HTTP/2 stream / network
       |
       v
Server queue + deserialization
       |
       v
Server interceptor + business handler
       |
       v
Response serialization + HTTP/2
       |
       v
Client deserialization + callback
       |
       v
RPC completed
```

Trong cùng một call, các giai đoạn có thể chồng lấp với hoạt động khác trên connection hoặc server executor. Sơ đồ biểu diễn các chặng logic, không phải một phép cộng thời gian chính xác cho mọi runtime.

Một unary call thường chịu overhead cố định cho call lifecycle, metadata, HTTP/2 framing và scheduling. Với request nhỏ, overhead này có thể chiếm tỷ trọng lớn hơn business logic. Với request lớn, serialization, allocation, network và parse có thể trở thành phần đáng kể.

Đo client end-to-end và server handler duration riêng giúp định vị:

- Client latency cao, server handler nhanh: xem client queue, network, TLS, serialization, connection hoặc server queue trước handler.
- Cả client và handler đều chậm: xem business dependency, CPU, lock, database và GC.
- Handler nhanh nhưng client p99 cao: điều tra queue trước/sau handler, transport, response parse và tail latency ở dependency.

## 4. Closed-loop và open-loop load test

Mô hình tạo tải ảnh hưởng trực tiếp tới kết quả:

**Closed-loop** giữ số client/worker đồng thời cố định. Một worker gửi call, đợi response rồi mới gửi call tiếp theo. Khi latency tăng, tốc độ phát request tự giảm. Mô hình này phù hợp mô phỏng một nhóm caller chờ response, nhưng có thể che giấu quá tải vì load generator tự giảm offered rate.

**Open-loop** cố gắng phát request theo arrival rate xác định, độc lập với thời gian hoàn thành của request trước. Mô hình này gần hơn với hệ thống nhận traffic liên tục. Khi server không theo kịp, queue và in-flight request tăng; cần giới hạn queue và ghi nhận request bị drop/reject.

| Thuộc tính | Closed-loop | Open-loop |
| --- | --- | --- |
| Cách tạo tải | Giữ concurrency, chờ call xong mới gửi tiếp | Giữ arrival rate mục tiêu |
| Khi latency tăng | Offered rate thường giảm | Offered rate vẫn giữ nếu generator đủ sức |
| Rủi ro đo | Che khuất queue buildup/overload | Có thể tạo queue lớn nếu không giới hạn |
| Phù hợp | Mô hình user/worker đồng bộ | Mô hình traffic đến liên tục, capacity và overload |

Một load test tốt thường dùng cả hai để hiểu hai kiểu hành vi. Với open-loop, ghi rõ request được schedule, thực sự bắt đầu, hoàn thành, drop hay timeout. Nếu chỉ đo latency của các request đã hoàn thành, bạn có thể bỏ qua những request bị queue quá lâu hoặc bị loại bỏ.

## 5. Coordinated omission và tải được phát đúng nhịp

Coordinated omission xảy ra khi load generator chỉ gửi request tiếp theo sau khi request trước hoàn tất. Trong lúc server bị chậm, generator cũng chậm lại và không tạo những request đáng lẽ đã đến trong khoảng thời gian đó. Kết quả có thể đánh giá thấp tail latency dưới tải liên tục.

Ví dụ server tạm dừng 2 giây vì GC. Closed-loop client có ít worker sẽ ngừng phát phần lớn request trong thời gian này. Open-loop client tiếp tục schedule theo arrival rate, qua đó cho thấy queueing và latency của traffic đến trong giai đoạn đình trệ.

Để tránh kết luận sai:

- Chọn load model theo traffic production.
- Với open-loop, ghi nhận scheduled time và actual start time nếu công cụ hỗ trợ.
- Báo cả queue delay và service latency khi có thể.
- Không loại bỏ timeout/drop khỏi báo cáo.
- Kiểm tra load generator không trở thành nút thắt CPU, network hoặc connection.

## 6. Concurrency, throughput và Little’s Law

Little’s Law liên hệ số request đang ở trong hệ thống với throughput và thời gian trung bình:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số request trung bình đang in-flight trong hệ thống.
- \(\lambda\): throughput trung bình, tính bằng request/giây.
- \(W\): thời gian trung bình một request ở trong hệ thống, tính bằng giây.

Ví dụ, nếu service hoàn thành 600 RPC/s và thời gian end-to-end trung bình là 50 ms (0,05 giây), số RPC in-flight trung bình xấp xỉ:

\[
L = 600 \times 0.05 = 30
\]

Nếu latency tăng lên 200 ms trong khi throughput vẫn là 600 RPC/s, số RPC in-flight trung bình tăng lên khoảng 120. Điều này có thể làm tăng queue, memory và contention. Little’s Law mô tả quan hệ trung bình trong hệ thống ổn định; không dùng nó để dự đoán tail latency hoặc một hệ thống đang mất ổn định.

Tăng concurrency có thể tăng throughput ban đầu vì CPU và network được sử dụng tốt hơn. Sau điểm bão hòa, concurrency thêm chủ yếu làm tăng queueing và latency, trong khi goodput gần như không tăng hoặc giảm.

## 7. Tái sử dụng channel và warm-up đúng cách

`ManagedChannel` là tài nguyên dài hạn, hỗ trợ nhiều RPC đồng thời và multiplex các stream trên HTTP/2 connection. Không tạo channel mới cho mỗi request. Việc tạo channel liên tục có thể lặp DNS resolution, TCP/TLS handshake, HTTP/2 setup, thread và buffer allocation.

Ví dụ client dùng một channel và tái sử dụng stub:

```java
ManagedChannel channel = ManagedChannelBuilder
    .forTarget("dns:///orders.default.svc.cluster.local:8443")
    .useTransportSecurity()
    .build();

OrderServiceGrpc.OrderServiceBlockingStub baseStub =
    OrderServiceGrpc.newBlockingStub(channel);

GetOrderResponse response = baseStub
    .withDeadlineAfter(300, TimeUnit.MILLISECONDS)
    .getOrder(request);
```

Generated stub là immutable; `withDeadlineAfter(...)` trả về stub cấu hình call mới và có thể tái sử dụng channel. Channel cần được đóng khi ứng dụng shutdown.

Trước khi benchmark:

1. Tạo channel một lần và đợi resolver phân giải target.
2. Gửi warm-up calls để hoàn tất kết nối, TLS handshake, JIT compilation và khởi tạo lazy resources.
3. Xác minh subchannel ở trạng thái `READY`.
4. Chỉ bắt đầu đo sau giai đoạn warm-up.
5. Giữ nguyên channel, stub pattern, TLS, compression và load balancing policy giữa các lần chạy.

Nếu mục tiêu là đo cold start, hãy đo riêng thời gian tạo channel/kết nối. Không trộn cold start với steady-state latency rồi gọi chung là unary latency.

## 8. Deadline, timeout và status khi đo

Mỗi RPC nên có deadline phù hợp với SLA. Deadline giới hạn thời gian client chờ kết quả và được truyền tới server để các dependency có thể hủy công việc khi call hết hạn. Không đặt deadline quá thấp chỉ để latency benchmark trông đẹp: request bị timeout sẽ làm goodput giảm và error rate tăng.

Khi phân tích kết quả, phân loại status:

| Status | Cách diễn giải khi benchmark |
| --- | --- |
| `OK` | RPC hoàn thành thành công; tính vào goodput |
| `DEADLINE_EXCEEDED` | Không hoàn thành trong deadline; ghi nhận như lỗi/timeout |
| `UNAVAILABLE` | Transport/backend tạm không khả dụng; kiểm tra reconnect và retry |
| `RESOURCE_EXHAUSTED` | Có thể chạm quota, message limit hoặc capacity protection |
| `INTERNAL` | Lỗi server; cần điều tra thay vì xem là latency bình thường |
| `CANCELLED` | Caller hoặc upstream hủy; phân biệt cancellation chủ động và do overload |

Không chỉ đo latency của các call trả `OK`. Một hệ thống có p50 thấp nhưng tỷ lệ `DEADLINE_EXCEEDED` cao không đạt SLA. Ghi nhận deadline, retry count và status cuối; nếu retry bật, phân biệt latency của một attempt với latency toàn logical RPC.

## 9. Đo tại client và server

Client là nguồn đo end-to-end quan trọng nhất vì nó quan sát thời gian mà caller thực sự trải qua. Có thể dùng `System.nanoTime()` quanh blocking call trong một phép đo đơn giản:

```java
long started = System.nanoTime();
try {
    GetOrderResponse response = stub
        .withDeadlineAfter(300, TimeUnit.MILLISECONDS)
        .getOrder(request);
    long elapsedNanos = System.nanoTime() - started;
    latencyHistogram.record(elapsedNanos);
} catch (StatusRuntimeException error) {
    errorCounter.increment(error.getStatus().getCode());
    throw error;
}
```

Đoạn code chỉ minh họa ranh giới end-to-end cho một call đồng bộ. Nó không phải load generator và không nên tạo histogram riêng cho mỗi request. Trong ứng dụng thực tế, dùng metrics library có histogram/bucket và tránh ghi log đồng bộ trong hot path.

Server interceptor có thể đo thời gian từ lúc nhận call đến khi call đóng. Đó là server-observed duration, có thể bao gồm queueing tùy vị trí instrumentation nhưng không bao gồm toàn bộ client-side delay. Dùng trace span hoặc timestamp có correlation để phân tích các chặng; đồng hồ giữa các máy có thể lệch nên không trừ timestamp tuyệt đối nếu chưa đồng bộ clock.

Không cộng client latency và server duration như hai phần độc lập nếu client latency đã bao gồm server duration. Chúng là hai góc quan sát có phần chồng lấp.

## 10. Thiết kế một benchmark có thể lặp lại

Một benchmark unary đáng tin cậy cần kiểm soát:

- **Workload:** method, request/response size, tỷ lệ cache hit/miss và business work giống thực tế.
- **Load model:** closed-loop hoặc open-loop; concurrency/arrival rate được ghi rõ.
- **Warm-up:** JVM, JIT, channel, TLS và connection đã ổn định.
- **Duration:** đủ dài để quan sát GC, autoscaling và dao động tải; bỏ giai đoạn warm-up khỏi phép đo.
- **Environment:** cùng CPU/memory limit, JVM flags, replica count, network path và dependency.
- **Load generator:** đủ tài nguyên, đặt gần đúng vị trí client production và không bão hòa trước server.
- **Reporting:** offered rate, started/completed, goodput, errors, p50/p95/p99, CPU, memory và GC.

Thay đổi một yếu tố mỗi lần, ví dụ concurrency, payload size, compression hoặc replica count. Chạy nhiều lần và so sánh median/variation giữa các run; ghi lại commit, cấu hình và dữ liệu thử để kết quả tái lập được.

## 11. Tìm điểm bão hòa và tối ưu

Tăng offered load theo từng bậc, giữ mỗi bậc đủ lâu để hệ thống ổn định. Vẽ goodput và p99 latency theo offered rate:

```text
Offered rate tăng
       |
       v
Goodput tăng gần tuyến tính
       |
       v
Đạt vùng capacity / saturation knee
       |
       +---- Goodput gần như đi ngang
       |
       +---- p95/p99 latency tăng nhanh
       |
       v
Queue, timeout và error tăng
```

Điểm mà p99 bắt đầu tăng nhanh trong khi goodput không tăng tương ứng là tín hiệu hệ thống tiến gần bão hòa. Không nên vận hành liên tục ngay tại knee; cần headroom cho burst, rollout và biến động dependency.

Chẩn đoán theo tài nguyên:

| Quan sát | Hướng điều tra |
| --- | --- |
| CPU server gần 100%, handler CPU-bound | Profile code, serialization, allocation và số worker |
| CPU thấp nhưng latency cao | Database, downstream RPC, lock, thread starvation hoặc network |
| Queue/executor tăng | Tăng năng lực xử lý hoặc giới hạn admission; không chỉ tăng queue |
| GC pause/allocation tăng | Message size, object churn, buffer copy và heap sizing |
| Một backend nóng hơn | Resolver/LB policy, connection reuse và phân phối request |
| Client CPU cao | Serialization, compression, interceptor hoặc load generator |
| `RESOURCE_EXHAUSTED` tăng | Quota, message limit, concurrency limit và flow control |

Tối ưu theo bottleneck đã đo: tái sử dụng channel; giảm payload không cần thiết; tránh blocking I/O trên executor không phù hợp; đặt pool và concurrency có giới hạn; dùng deadline; kiểm tra load balancing; và scale out khi workload thực sự phân tán được. Tăng thread hoặc queue mà không hiểu bottleneck có thể làm context switching và tail latency xấu hơn.

## 12. Bài tập vận dụng

`OrderService.GetOrder` có p50 = 22 ms, p99 = 480 ms ở mức 700 RPC/s. Khi tăng offered rate lên 1.000 RPC/s, goodput chỉ tăng tới 740 RPC/s, p99 vượt 1 giây và `DEADLINE_EXCEEDED` tăng. CPU server ở mức 85%, một replica có traffic cao hơn các replica còn lại.

**Yêu cầu:**

1. Xác định các metric bổ sung cần thu thập ở client, server, resolver và load balancer.
2. Thiết kế cả closed-loop và open-loop test để xác định liệu load generator có che giấu queueing hay không.
3. Tính số RPC in-flight trung bình ở 700 RPC/s với latency trung bình 40 ms bằng Little’s Law.
4. Kiểm tra channel reuse, HTTP/2 connection, resolver result và load balancing policy để tìm nguyên nhân replica nóng.
5. Phân tích server CPU, executor queue, downstream latency, allocation và GC trước khi tăng thread.
6. Đánh giá deadline/retry để tránh làm tăng tải khi backend đã bão hòa.
7. Đề xuất capacity headroom và ngưỡng cảnh báo dựa trên goodput, p99, error rate và queue.

**Câu hỏi tự kiểm tra:**

- End-to-end latency khác server handler duration thế nào?
- Vì sao cần báo goodput cùng offered rate?
- p50 thấp nhưng p99 cao nói lên điều gì?
- Closed-loop có thể che giấu overload ra sao?
- Coordinated omission làm sai lệch phép đo như thế nào?
- Little’s Law liên hệ throughput, latency và in-flight request ra sao?
- Vì sao phải warm up channel/JVM trước steady-state benchmark?
- Làm thế nào nhận biết saturation knee?
- Khi bật retry, cần phân biệt latency attempt với logical RPC thế nào?

**Ghi nhớ:** Unary latency phản ánh thời gian caller chờ một RPC; throughput phải dựa trên số call hoàn thành, đặc biệt là goodput. Đo percentile và error rate cùng offered rate; chọn closed-loop/open-loop phù hợp; tái sử dụng channel và warm-up trước khi đo. Tăng tải theo bậc để tìm saturation knee, dùng Little’s Law và telemetry client/server để định vị queueing, rồi tối ưu đúng bottleneck thay vì chỉ tăng concurrency.
