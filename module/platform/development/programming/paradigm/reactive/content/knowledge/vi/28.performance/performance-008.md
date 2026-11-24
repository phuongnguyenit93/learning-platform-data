# Đo thông lượng và các phân vị độ trễ trong điều kiện tải

Một pipeline reactive có thể hoàn tất rất nhanh trong test nhỏ nhưng suy giảm rõ rệt khi nhiều request đến cùng lúc. Để đánh giá hiệu năng, cần đo ít nhất hai khía cạnh: hệ thống xử lý được bao nhiêu công việc trong một đơn vị thời gian và người gọi phải chờ bao lâu cho mỗi công việc. Thông lượng (*throughput*) cho biết tốc độ xử lý; độ trễ (*latency*) mô tả thời gian phản hồi của từng request. Khi tải tăng, hai đại lượng này phải được đọc cùng với tỷ lệ lỗi, số request đang chạy và mức sử dụng tài nguyên.

Giá trị trung bình không mô tả đầy đủ trải nghiệm của người dùng. Một hệ thống có latency trung bình thấp vẫn có thể có một nhóm request rất chậm. Vì vậy, cần xem các phân vị như p50, p90, p95 và p99, đo trong một khoảng tải ổn định và với workload đại diện. Với Project Reactor, việc đo cũng cần chú ý tới subscription, cancellation, backpressure, scheduler, connection pool và các hàng đợi nằm giữa những thành phần bất đồng bộ.

## 1. Xác định rõ các đại lượng cần đo

Trước khi chạy tải, hãy định nghĩa mỗi metric bắt đầu và kết thúc ở đâu. Nếu không có định nghĩa thống nhất, hai lần benchmark có thể đo những khoảng thời gian khác nhau và không thể so sánh.

| Đại lượng | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| Offered throughput | Tốc độ load generator gửi request vào hệ thống | Mức tải được yêu cầu |
| Achieved throughput | Số request hệ thống hoàn tất trong một giây | Tốc độ hệ thống thực sự xử lý được |
| Successful throughput | Số request hoàn tất thành công trong một giây | Tốc độ phục vụ hữu ích |
| Error rate | Tỷ lệ request kết thúc bằng lỗi, timeout hoặc response không đạt hợp đồng | Độ tin cậy dưới tải |
| Latency | Thời gian từ mốc bắt đầu tới mốc hoàn tất đã định nghĩa | Thời gian người gọi phải chờ |
| In-flight requests | Số request đang được xử lý tại một thời điểm | Mức concurrency thực tế |
| Queue depth | Số tác vụ đang chờ trong các hàng đợi | Dấu hiệu tích lũy công việc |

Với HTTP API, latency phía client thường được đo từ lúc client bắt đầu gửi request tới khi nhận đủ response body. Server-side timer có thể chỉ đo thời gian xử lý trong ứng dụng, không bao gồm DNS, TCP/TLS, gateway, mạng hoặc thời gian client đọc body. Hãy ghi rõ đang báo cáo latency end-to-end hay thời gian nội bộ của service.

Với endpoint streaming như NDJSON hoặc SSE, một request có thể tồn tại lâu và phát nhiều phần tử. Khi đó, đo riêng thời gian tới byte đầu tiên (*time to first byte*), khoảng cách giữa các phần tử, thời gian stream tồn tại và thời gian tới phần tử cuối. Không so sánh thời gian hoàn tất của một stream vô hạn với latency của một request trả JSON hữu hạn.

## 2. Thông lượng là số công việc hoàn tất trên một đơn vị thời gian

Thông lượng thường được biểu diễn bằng request/second (RPS), operation/second hoặc message/second. Nếu trong khoảng đo có 12.000 request hoàn tất trong 60 giây, throughput đạt được là:

\[
\text{throughput} = \frac{12.000}{60} = 200\ \text{request/second}
\]

Nên báo cáo riêng tổng throughput và successful throughput. Nếu load generator gửi 300 RPS nhưng service chỉ hoàn tất 180 RPS thành công, phần còn lại có thể đang chờ, timeout, bị từ chối hoặc kết thúc bằng lỗi. Chỉ nhìn tổng số request được gửi sẽ đánh giá quá cao năng lực phục vụ.

Trong khoảng tải ổn định, có thể tính throughput từ counter hoàn tất:

\[
\text{successful RPS} = \frac{\Delta\text{successful requests}}{\Delta t}
\]

Không tính request đang in-flight như request đã hoàn tất. Với retry, cần quyết định metric đếm một logical request của caller hay từng attempt tới dependency. Hai góc nhìn đều hữu ích nhưng phải đặt tên riêng để tránh đếm retry thành nhiều request thành công của người dùng.

## 3. Đọc phân vị độ trễ thay vì chỉ nhìn trung bình

Phân vị pX là ngưỡng mà X phần trăm mẫu có latency nhỏ hơn hoặc bằng ngưỡng đó. Ví dụ:

- p50 là trung vị: một nửa request nhanh hơn hoặc bằng giá trị này.
- p90 nghĩa là 90% request hoàn tất trong ngưỡng đó.
- p95 nghĩa là 95% request hoàn tất trong ngưỡng đó.
- p99 nghĩa là 99% request hoàn tất trong ngưỡng đó; 1% còn lại chậm hơn.

Giả sử kết quả đo có p50 = 45 ms, p95 = 180 ms và p99 = 900 ms. Phần lớn request phản hồi nhanh, nhưng một nhóm nhỏ có độ trễ cao hơn nhiều. Nếu chỉ báo cáo trung bình 70 ms, tail latency gần một giây sẽ bị che khuất.

| Metric | Câu hỏi trả lời |
| --- | --- |
| p50 | Trải nghiệm điển hình ở giữa phân phối ra sao? |
| p90/p95 | Nhóm request chậm hơn bình thường đang ở mức nào? |
| p99 | Tail latency có ảnh hưởng tới SLA/SLO không? |
| max | Có outlier cực đoan nào cần điều tra không? |
| mean | Tổng thời gian trung bình trên mỗi request là bao nhiêu? |

Phân vị không thể cộng hoặc lấy trung bình giữa các máy một cách chính xác. Ví dụ, không thể lấy trung bình p99 của instance A và p99 của instance B để suy ra p99 toàn hệ thống. Muốn tổng hợp phân vị trên nhiều instance, hãy thu thập histogram bucket có thể gộp rồi tính quantile từ histogram tổng hợp, hoặc dùng một hệ thống đo phân phối tập trung phù hợp.

Kết quả p99 cũng cần đủ số mẫu. Nếu chỉ có vài trăm request, phần 1% đuôi phân phối chỉ chứa một vài quan sát nên p99 dao động mạnh. Hãy chạy đủ lâu và tạo đủ request để tail percentile có số mẫu đáng tin cậy; đồng thời báo cáo số lượng mẫu cùng khoảng thời gian đo.

## 4. Chọn workload model phù hợp

Hai mô hình tải thường gặp là closed workload và open workload.

**Closed workload** có số lượng virtual user cố định. Mỗi user gửi request, chờ response xong rồi mới gửi request tiếp theo. Khi service chậm, chính tốc độ phát request của generator cũng giảm. Mô hình này phù hợp với một nhóm người dùng có hành vi chờ kết quả trước khi thao tác tiếp.

**Open workload** tạo request theo tốc độ đến được định trước, không giảm tốc độ chỉ vì response chậm. Ví dụ hệ thống nhận trung bình 500 request mỗi giây từ nhiều client độc lập. Mô hình này phù hợp để kiểm tra khả năng chịu tải theo arrival rate và phát hiện điều gì xảy ra khi tải đến vượt năng lực xử lý.

| Mô hình | Điều khiển | Điểm mạnh | Rủi ro khi dùng sai |
| --- | --- | --- | --- |
| Closed | Số user/concurrency cố định | Gần với người dùng chờ response rồi thao tác tiếp | Có thể giảm offered load khi service chậm và che khuất quá tải |
| Open | Arrival rate hoặc request/second cố định | Cho thấy hệ thống phản ứng thế nào trước tốc độ request độc lập | Cần giới hạn generator và xử lý backlog của chính công cụ tạo tải |

Với open workload, nếu hệ thống chỉ hoàn tất 300 RPS trong khi generator tiếp tục gửi 500 RPS, số request chờ có thể tăng liên tục. Đó là dấu hiệu hệ thống không đạt trạng thái ổn định ở mức tải đó. Đừng chỉ ghi latency của những request đã hoàn tất mà bỏ qua request vẫn đang chờ hoặc bị loại khỏi thống kê.

## 5. Tránh coordinated omission trong load test

Coordinated omission xảy ra khi load generator chỉ gửi request mới sau khi request trước hoàn tất, hoặc bỏ qua những thời điểm lẽ ra phải phát request trong lúc hệ thống đang chậm. Khi service bị pause hoặc quá tải, generator cũng chậm theo và không ghi nhận đầy đủ các request lẽ ra đã phải chờ. Kết quả latency có thể trông tốt hơn thực tế.

Để giảm hiện tượng này:

- Dùng open workload khi arrival rate của người dùng độc lập với response time.
- Ghi nhận offered load, achieved throughput và số request đang chờ cùng lúc.
- Chọn công cụ có cơ chế lập lịch arrival rate và cách tính latency phù hợp; đọc rõ cách công cụ xử lý request bị trễ lịch.
- Không loại bỏ timeout hoặc request thất bại khỏi báo cáo tail latency mà không báo riêng tỷ lệ bị loại.
- Theo dõi độ trễ phát request của generator; generator không phát đúng lịch cũng có thể làm sai phép đo.

Closed workload vẫn hữu ích cho các kịch bản người dùng thực sự chờ response. Nhưng khi dùng nó để xác định capacity, cần hiểu rằng số request đến có thể giảm theo latency và không mô phỏng được một luồng request bên ngoài tiếp tục đến đều.

## 6. Thiết kế các pha của một bài đo tải

Một bài đo có thể gồm nhiều pha, mỗi pha trả lời một câu hỏi khác nhau:

1. **Baseline:** tải thấp để xác nhận hệ thống hoạt động đúng và lấy latency nền.
2. **Warm-up:** tạo tải vừa đủ để JVM JIT, connection pool, cache và các thành phần lazy ổn định.
3. **Ramp-up:** tăng dần arrival rate hoặc concurrency để quan sát xu hướng.
4. **Steady state:** giữ một mức tải đủ lâu để throughput, latency và tài nguyên có thể được quan sát trong trạng thái tương đối ổn định.
5. **Stress:** tăng vượt mức dự kiến để tìm điểm bão hòa và hành vi khi quá tải.
6. **Spike:** tăng tải đột ngột để kiểm tra khả năng hấp thụ burst và phục hồi.
7. **Soak:** giữ tải dài hơn để phát hiện memory leak, queue tăng dần, connection không được trả hoặc suy giảm theo thời gian.
8. **Cool-down:** giảm tải và quan sát hệ thống có giải phóng backlog, connection và tài nguyên hay không.

Không dùng thời gian warm-up làm kết quả chính nếu JVM, cache hoặc pool chưa ổn định. Ghi rõ thời lượng từng pha, ramp profile, arrival rate/concurrency, số worker của generator và điều kiện dừng. Chạy lại các lần đo để xác định biến thiên tự nhiên thay vì kết luận từ một lần chạy.

## 7. Chọn công cụ theo loại phép đo

Load test và microbenchmark trả lời hai câu hỏi khác nhau:

| Công cụ/nhóm công cụ | Phạm vi phù hợp | Không nên dùng để kết luận |
| --- | --- | --- |
| Gatling, k6, JMeter hoặc công cụ HTTP load test tương đương | Throughput và latency của API dưới workload thực tế | Chi phí vài nanosecond của một method đơn lẻ |
| wrk/vegeta hoặc HTTP benchmark tương đương | Kiểm tra nhanh capacity của endpoint và server | Đo chính xác hành vi nghiệp vụ nhiều bước nếu script không mô phỏng chúng |
| JMH | Microbenchmark method, codec, mapper hoặc thuật toán trong JVM | Capacity end-to-end của hệ thống gồm network/database |
| WebTestClient/StepVerifier | Kiểm tra semantics và hành vi publisher | Thay thế một load generator cho tải production-like |

JMH xử lý warm-up, fork và các vấn đề đo microbenchmark của JVM tốt hơn một vòng lặp `System.nanoTime()` tự viết. Nhưng benchmark method không bao gồm connection pool, HTTP transport, database, gateway hoặc load distribution. Muốn đo API reactive dưới tải, hãy dùng load generator bên ngoài process ứng dụng và mô phỏng request/response theo giao thức thật.

## 8. Đo latency ở phía ứng dụng bằng Micrometer

Micrometer `Timer` có thể ghi thời lượng và số lần hoàn tất. Đặt việc tạo sample bên trong `Mono.defer` để mỗi subscription có một sample riêng:

```java
Timer requestTimer = Timer.builder("orders.lookup.duration")
    .description("Thời gian xử lý lookup đơn hàng")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(50),
        Duration.ofMillis(100),
        Duration.ofMillis(250),
        Duration.ofSeconds(1)
    )
    .register(registry);

Counter completed = registry.counter("orders.lookup.completed");
Counter failed = registry.counter("orders.lookup.failed");
Counter cancelled = registry.counter("orders.lookup.cancelled");

Mono<Order> measuredLookup(String id) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(registry);
        return orderService.findById(id)
            .doFinally(signal -> {
                sample.stop(requestTimer);
                switch (signal) {
                    case ON_COMPLETE -> completed.increment();
                    case ON_ERROR -> failed.increment();
                    case CANCEL -> cancelled.increment();
                    default -> { }
                }
            });
    });
}
```

`Timer` ghi thời lượng từ lúc tạo sample tới khi `doFinally` chạy. Ví dụ này tính cả thời gian tới cancellation; các counter riêng giúp phân biệt complete, error và cancel. Nếu SLA chỉ tính response thành công, hãy định nghĩa metric thành công riêng hoặc lọc outcome phù hợp thay vì gộp mọi thời điểm kết thúc vào một con số không giải thích được.

Trong code thực tế, `registry` là `MeterRegistry` được inject. Các metric nên dùng tên và tag có cardinality thấp, ví dụ `operation`, `route`, `dependency` hoặc `outcome` với tập giá trị hữu hạn. Không gắn `userId`, `orderId`, email hoặc URL có ID động vào tag vì số time series có thể tăng không giới hạn.

Timer ở tầng service không thay thế phép đo end-to-end của load generator. Hãy dùng cả hai: client-side latency phản ánh trải nghiệm gọi; server-side timer giúp khoanh vùng thời gian bên trong ứng dụng.

## 9. Histogram và percentile cần được cấu hình có chủ đích

Micrometer có thể xuất percentile histogram hoặc percentile được tính tại process. Hai cách có khác biệt:

- Histogram bucket ghi số quan sát trong các khoảng thời gian. Các bucket có thể được tổng hợp qua nhiều instance rồi tính quantile ở backend hỗ trợ histogram.
- Client-side percentile được tính tại từng meter/process theo cửa sổ thống kê. Các percentile riêng lẻ không thể gộp chính xác thành percentile toàn cụm bằng phép trung bình.

Với hệ thống nhiều instance, histogram thường phù hợp hơn khi cần tính p95/p99 ở cấp service. Cấu hình bucket/SLO nên bao phủ các ngưỡng có ý nghĩa với SLA và vùng latency thực tế; nếu bucket quá thô, percentile ước lượng sẽ kém chính xác. Nếu chỉ bật percentile tại từng instance, hãy hiểu rõ dashboard đang hiển thị instance đơn lẻ hay giá trị tổng hợp không hợp lệ.

Ví dụ truy vấn Prometheus thường dùng `histogram_quantile` trên histogram bucket đã tổng hợp. Tên metric thực tế phụ thuộc registry và cấu hình export:

```promql
histogram_quantile(
  0.99,
  sum by (le) (rate(orders_lookup_duration_seconds_bucket[5m]))
)
```

Throughput có thể được tính từ rate của counter request hoàn tất:

```promql
sum(rate(orders_lookup_completed_total[1m]))
```

Hãy kiểm tra tên metric được exporter tạo ra trong môi trường thực tế; ví dụ trên minh họa cấu trúc truy vấn, không bảo đảm tên metric luôn giống hệt ở mọi cấu hình.

## 10. Theo dõi cả hệ thống, không chỉ Timer của endpoint

Khi latency tăng hoặc throughput đạt plateau, cần đối chiếu nhiều tín hiệu để tìm tài nguyên bão hòa:

| Nhóm | Metric nên quan sát | Dấu hiệu cần chú ý |
| --- | --- | --- |
| JVM | CPU, heap, allocation rate, GC pause, thread count | CPU gần đầy, GC pause dài, heap tăng liên tục |
| Reactor/scheduler | Worker active, task queued, rejected task, scheduler delay | Queue tăng, tác vụ bị từ chối, worker bị chiếm lâu |
| Database | Connection pool active/idle/pending, query latency, lock wait | Pool cạn, pending acquire tăng, query/lock chậm |
| HTTP client | Connection pool, pending acquire, response time, timeout | Request chờ connection, timeout tăng |
| Network | Throughput, retransmission, connection count, TLS cost | Băng thông hoặc connection trở thành giới hạn |
| Application | In-flight request, queue depth, error rate, per-route latency | Một route hoặc dependency tạo tail latency |
| Load generator | CPU, network, event loop, dropped/late request | Công cụ tạo tải không đủ sức phát workload đã cấu hình |

Trong Reactor, một pipeline non-blocking không có nghĩa là toàn hệ thống không có hàng đợi. `flatMap` concurrency, `prefetch`, `onBackpressureBuffer`, scheduler queue, connection pool và queue của client đều có thể giữ công việc. Theo dõi vị trí queue tăng giúp xác định bottleneck thay vì chỉ tăng thread hoặc tăng concurrency theo cảm tính.

## 11. Backpressure và concurrency ảnh hưởng tới kết quả đo

Reactive Streams cho phép downstream điều khiển demand bằng `request(n)`, nhưng backpressure không tự động giới hạn mọi tài nguyên của ứng dụng. Ví dụ:

```java
Flux<Result> results = requests.flatMap(
    request -> remoteClient.call(request),
    16
);
```

Concurrency 16 giới hạn số inner publisher hoạt động đồng thời tại `flatMap`. Nếu mỗi inner gọi thêm hai dependency, số request downstream đang chạy có thể cao hơn 16. Nếu bên trong có buffer hoặc client connection pool, dữ liệu vẫn có thể chờ ở những tầng khác.

Khi benchmark, thử nhiều mức concurrency có kiểm soát, chẳng hạn 1, 4, 8, 16 và 32, rồi ghi lại throughput, p95/p99, error rate và tài nguyên. Tăng concurrency có thể cải thiện throughput khi hệ thống còn nhàn, nhưng sau điểm bão hòa thường làm queue và tail latency tăng. Chọn cấu hình tại vùng đạt throughput hữu ích mà latency và lỗi vẫn nằm trong ngưỡng chấp nhận.

Không dùng `onBackpressureBuffer()` như cách chữa quá tải mặc định. Buffer không giới hạn có thể biến overload thành tăng heap và GC; buffer giới hạn cần chính sách rõ khi đầy như drop, error hoặc xử lý chậm. Mọi phép đo nên ghi nhận số phần tử bị drop, overflow và request bị từ chối nếu có.

## 12. Dùng Little's Law để kiểm tra tính nhất quán

Trong một hệ thống ổn định, Little's Law mô tả quan hệ giữa số công việc trung bình đang ở trong hệ thống (L), throughput trung bình (λ) và thời gian lưu lại trung bình (W):

\[
L = \lambda \times W
\]

Ví dụ, nếu hệ thống hoàn tất trung bình 200 request/giây và thời gian phản hồi trung bình là 0,25 giây, số request trung bình đang in-flight xấp xỉ:

\[
L = 200 \times 0,25 = 50\ \text{request}
\]

Đây là quan hệ ở trạng thái ổn định và dùng thời gian trung bình, không thay p95 hoặc p99 vào công thức để suy ra số request chính xác. Nếu in-flight hoặc queue depth tăng liên tục trong khi throughput không tăng, hệ thống chưa ở trạng thái ổn định tại mức offered load đó. Hãy giảm tải hoặc phân tích điểm nghẽn thay vì lấy một lát cắt ngắn làm kết quả capacity.

## 13. Ví dụ một kịch bản load test có arrival rate

Một kịch bản open workload cần giữ tốc độ gửi request độc lập với thời gian phản hồi. Ví dụ dưới đây dùng cú pháp k6 để minh họa một bài đo HTTP với tốc độ đến được cấu hình trước:

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    orders: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 50,
      maxVUs: 300,
    },
  },
};

export default function () {
  const response = http.get('http://localhost:8080/orders/42');
  check(response, {
    'status is 200': (r) => r.status === 200,
  });
}
```

Kịch bản này yêu cầu generator tạo 200 iteration mỗi giây trong năm phút và có thể tăng virtual user trong giới hạn đã đặt để duy trì arrival rate. Cần kiểm tra metric dropped iterations hoặc request không được phát đúng lịch; nếu generator không đủ VU, CPU hoặc network, offered load thực tế sẽ thấp hơn cấu hình.

Đây chỉ là ví dụ endpoint. Một benchmark có giá trị phải dùng dữ liệu và phân phối request đại diện, xác thực response body theo yêu cầu, quản lý token/session nếu có, tránh cache key đơn nhất làm sai lệch tải và chạy generator ở môi trường đủ năng lực. Không dùng một script đơn giản để kết luận toàn bộ capacity của hệ thống nghiệp vụ.

## 14. Phân tích đường cong throughput và latency

Khi tăng offered load, một hệ thống khỏe thường có throughput tăng gần tương ứng trong vùng chưa bão hòa. Khi một tài nguyên đạt giới hạn, throughput bắt đầu tăng chậm hoặc giữ plateau; latency, queue depth và error rate có thể tăng nhanh.

```text
Throughput
   ^                         ________  <- vùng bão hòa
   |                    ____/
   |               ____/
   |          ____/
   |     ____/
   +----------------------------------> Offered load

Latency
   ^                              /
   |                           __/
   |                       ___/
   |                  ____/
   |_________________/
   +----------------------------------> Offered load
```

Đồ thị chỉ mang tính khái niệm. Điểm bão hòa có thể do CPU, database, connection pool, network, scheduler queue hoặc dependency ngoài. Hãy đối chiếu các metric để tìm tài nguyên đầu tiên đạt giới hạn. Không chọn capacity chỉ theo mức throughput cao nhất nếu p99 hoặc error rate đã vượt SLO.

Một báo cáo capacity tốt thường xác định vùng vận hành an toàn: throughput thành công đạt mục tiêu, p95/p99 nằm trong ngưỡng, error rate thấp, queue không tăng liên tục và tài nguyên còn đủ headroom cho burst. Mức tối đa trong một bài stress test không nhất thiết là mức tải nên vận hành thường xuyên.

## 15. Các lỗi thường làm sai phép đo

- Đo quá ngắn, không warm-up JVM hoặc không chờ hệ thống vào steady state.
- Chỉ báo cáo average latency mà bỏ qua p95/p99.
- Không phân biệt offered throughput với achieved/successful throughput.
- Dùng closed workload để kết luận capacity cho một hệ thống nhận arrival rate độc lập mà không giải thích giới hạn của mô hình.
- Bỏ request timeout, dropped iteration hoặc lỗi khỏi phân phối mà không báo tỷ lệ.
- Load generator bị bão hòa CPU/network nhưng vẫn kết luận server đã đạt giới hạn.
- So sánh hai lần chạy với dữ liệu, cache, JVM flags, connection pool hoặc môi trường khác nhau.
- Gộp percentile của nhiều instance bằng phép trung bình.
- Đo thời gian xử lý nội bộ rồi gọi đó là end-to-end latency.
- Tạo một request duy nhất hoặc một cache key duy nhất khiến cache hit rate không đại diện.
- Tăng `flatMap` concurrency hoặc buffer mà không đo queue và tail latency.
- Dùng JMH để kết luận throughput của HTTP/database end-to-end.

## 16. Quy trình chạy và ghi lại một benchmark có thể lặp lại

Trước khi chạy, ghi rõ phiên bản ứng dụng, commit, JVM, CPU/memory, cấu hình container, database, connection pool, scheduler, số instance và cấu hình load generator. Dùng cùng môi trường và cùng dataset khi so sánh hai phiên bản.

Trong mỗi lần chạy:

1. Xác nhận health check, dữ liệu test và kết nối dependency.
2. Warm-up để JIT, pool và cache đạt trạng thái phù hợp.
3. Chạy ramp-up theo profile đã định.
4. Giữ steady-state đủ lâu để thu thập đủ mẫu cho tail percentile.
5. Ghi offered/achieved/successful RPS, p50/p95/p99, max, error/timeout rate và dropped requests.
6. Ghi CPU, heap/GC, in-flight, scheduler queue, connection pool và queue depth.
7. Lặp lại bài đo và so sánh độ biến thiên giữa các lần chạy.
8. Chạy stress hoặc soak riêng để tìm giới hạn và vấn đề theo thời gian.

Một bảng kết quả tối thiểu có thể có dạng:

| Offered RPS | Successful RPS | p50 | p95 | p99 | Error rate | CPU | Ghi chú |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 100 | 99 | 35 ms | 70 ms | 110 ms | 0,1% | 35% | Chưa bão hòa |
| 200 | 198 | 42 ms | 95 ms | 170 ms | 0,2% | 58% | Vùng ổn định |
| 300 | 275 | 80 ms | 320 ms | 900 ms | 4,0% | 92% | Bắt đầu bão hòa |

Các con số trên chỉ minh họa cách đọc bảng, không phải benchmark của một ứng dụng thực tế. Trong báo cáo thật, ghi thời gian đo, số mẫu, cấu hình workload và nguồn metric để người khác có thể tái hiện.

## 17. Chọn công cụ và metric theo câu hỏi cần trả lời

| Câu hỏi | Phép đo phù hợp |
| --- | --- |
| Một endpoint chịu được bao nhiêu request/giây? | Open/closed load test có offered và achieved RPS |
| Người dùng chậm nhất đang trải nghiệm thế nào? | p95/p99 end-to-end latency và error rate |
| Scheduler blocking có bị nghẽn không? | Active worker, queued task, rejected task và latency của đoạn blocking |
| Database có là bottleneck không? | Pool active/pending, query latency, lock wait và throughput database |
| Một operator có chi phí CPU cao không? | JMH microbenchmark hoặc profiling trong điều kiện kiểm soát |
| Stream phản hồi sớm hay bị buffer toàn bộ? | Time-to-first-element, inter-arrival gap, memory và cancellation |
| Tải dài có làm rò rỉ tài nguyên không? | Soak test, heap trend, connection/queue trend và GC |

Đo throughput và latency không phải chỉ chạy một lệnh benchmark rồi lấy con số cao nhất. Cần chọn workload đúng, kiểm soát môi trường, quan sát toàn bộ đường đi của request và đọc tail percentile cùng error rate. Trong ứng dụng Reactor, hãy đo cả demand/concurrency và các hàng đợi ở scheduler, client, database; một pipeline non-blocking vẫn có thể bão hòa khi công việc đến nhanh hơn tốc độ hoàn tất. Khi các metric được định nghĩa rõ và bài đo có thể lặp lại, nhóm phát triển mới có cơ sở để chọn concurrency, pool size và giới hạn tải theo bằng chứng.
