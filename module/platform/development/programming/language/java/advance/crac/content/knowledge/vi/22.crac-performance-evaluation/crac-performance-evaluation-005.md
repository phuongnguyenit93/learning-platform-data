# Đo độ trễ p50, p95, p99 và thông lượng sau restore

Sau khi khôi phục một ứng dụng Java từ checkpoint CRaC, cần đo xem ứng dụng thực sự phục vụ request nhanh và ổn định đến đâu. Việc JVM restore thành công hoặc endpoint health trả về HTTP 200 chưa đủ để kết luận hiệu năng tốt. Ứng dụng có thể cần thời gian tạo lại connection pool, nạp credential, làm nóng cache, khởi động worker hoặc đạt trạng thái xử lý ổn định. Trong giai đoạn đó, độ trễ của request đầu tiên có thể cao hơn nhiều so với độ trễ khi hệ thống đã ổn định.

Ba percentile thường được dùng là p50, p95 và p99. p50 mô tả độ trễ ở giữa phân bố; p95 cho biết 95% request hoàn tất trong khoảng thời gian không vượt quá giá trị đó; p99 tập trung vào nhóm request chậm nhất. Thông lượng cho biết hệ thống hoàn tất được bao nhiêu request hoặc operation trong một đơn vị thời gian. Khi đánh giá sau restore, cần đo cả latency và throughput vì một hệ thống có thể giữ latency thấp bằng cách xử lý ít request, hoặc đạt throughput cao nhưng tạo ra tail latency rất lớn.

Một phép đo có ý nghĩa phải tách rõ thời gian restore, thời gian từ restore tới readiness, độ trễ của request đầu tiên, độ trễ trong giai đoạn warm-up và độ trễ steady-state. Đồng thời, cần kiểm soát tải gửi vào, số request thành công, số lỗi, môi trường chạy và trạng thái dependency. Tài liệu này trình bày cách thiết kế phép đo, thu thập histogram, tính percentile, đo thông lượng và so sánh kết quả sau restore với baseline.

## 1. Những đại lượng cần đo

Không gộp mọi khoảng thời gian thành một con số gọi chung là startup latency. Với CRaC, có nhiều mốc khác nhau và mỗi mốc trả lời một câu hỏi vận hành riêng.

### 1.1. Restore duration

Restore duration là thời gian từ lúc bắt đầu lệnh hoặc API restore tới khi runtime khôi phục tiến trình và chuyển quyền điều khiển cho ứng dụng. Giá trị này phản ánh chi phí của checkpoint engine, việc đọc ảnh, dựng lại memory mapping và khôi phục trạng thái tiến trình.

Không phải mọi runtime đều cung cấp cùng một event hoặc metric cho mốc bắt đầu/kết thúc restore. Hãy dùng log hoặc telemetry của engine/JDK nếu có; nếu chỉ đo từ bên ngoài, ghi rõ điểm bắt đầu và điểm kết thúc đang dùng. Không gọi thời gian từ khi container được tạo tới readiness là restore duration thuần túy.

### 1.2. Restore-to-ready duration

Restore-to-ready là khoảng thời gian từ khi ứng dụng tiếp tục chạy sau restore tới khi readiness mở. Khoảng này có thể bao gồm:

- Callback afterRestore của CRaC Resource.
- Tạo lại database pool, HTTP client, broker client và socket.
- Lấy credential mới hoặc xác minh certificate.
- Đọc metadata của replica hiện tại.
- Nạp hoặc làm mới cache.
- Tham gia consumer group hoặc xin lease.
- Health check các dependency bắt buộc.

Đây thường là đại lượng quan trọng với hệ thống orchestration vì nó quyết định thời gian instance có thể nhận traffic.

### 1.3. First-request latency

First-request latency là độ trễ của request đầu tiên hoặc nhóm request đầu tiên sau khi readiness mở. Request đầu tiên có thể kích hoạt lazy initialization, tạo connection mới, tải class chưa được dùng, tạo cache entry hoặc thực hiện DNS/TLS handshake.

Không nên chỉ đo một request đầu tiên duy nhất. Hãy đo một cửa sổ first-request, ví dụ 10, 100 hoặc 1.000 request đầu tiên tùy lưu lượng và loại dịch vụ. Ghi rõ cửa sổ này bắt đầu ở thời điểm readiness mở hay ở thời điểm request đầu tiên được gửi.

### 1.4. Warm-up latency

Warm-up latency mô tả độ trễ trong khi ứng dụng chuyển từ trạng thái vừa restore sang trạng thái ổn định. Trong giai đoạn này, cache có thể được nạp, connection pool tăng số connection, JIT có thể tiếp tục tối ưu code và các dependency có thể đang phục hồi.

Hãy đo latency theo các cửa sổ thời gian hoặc theo số request kể từ readiness. Không loại bỏ giai đoạn này khỏi báo cáo nếu người dùng thực tế có thể gửi request trong lúc warm-up.

### 1.5. Steady-state latency

Steady-state latency là độ trễ khi ứng dụng đã đạt điều kiện ổn định được định nghĩa trước, ví dụ:

- Tỷ lệ cache hit đã đạt mức mục tiêu.
- Connection pool đã có đủ connection theo cấu hình.
- Worker và consumer đã hoạt động.
- Không còn bootstrap task bắt buộc.
- CPU, memory và request rate không còn xu hướng tăng/giảm lớn trong cửa sổ quan sát.

Không tự chọn một khoảng warm-up tùy ý rồi gọi phần còn lại là steady-state. Hãy định nghĩa điều kiện ổn định bằng metric hoặc trạng thái ứng dụng.

### 1.6. Throughput và goodput

Throughput là số request hoặc operation hoàn tất trong một đơn vị thời gian. Goodput là số operation hoàn tất thành công theo hợp đồng nghiệp vụ trong cùng khoảng thời gian.

Nên báo cáo riêng:

- Offered rate: tốc độ load generator dự định gửi.
- Accepted rate: tốc độ ứng dụng chấp nhận hoặc đưa request vào xử lý.
- Completed throughput: tốc độ request hoàn tất, kể cả lỗi nếu định nghĩa metric tính tất cả response hoàn tất.
- Successful throughput/goodput: tốc độ request hoàn tất thành công.
- Error rate: tỷ lệ request thất bại hoặc bị timeout.

Một service trả về lỗi nhanh vẫn có thể có completed throughput cao. Vì vậy, không dùng riêng requests/second để kết luận hiệu năng tốt.

## 2. Hiểu đúng p50, p95 và p99

Percentile mô tả vị trí trong phân bố độ trễ. Với tập mẫu latency được sắp xếp tăng dần:

- p50 là giá trị mà khoảng 50% mẫu có latency nhỏ hơn hoặc bằng.
- p95 là giá trị mà khoảng 95% mẫu có latency nhỏ hơn hoặc bằng.
- p99 là giá trị mà khoảng 99% mẫu có latency nhỏ hơn hoặc bằng.

Ví dụ:

| Percentile | Latency | Diễn giải |
|---|---:|---|
| p50 | 18 ms | Một nửa request hoàn tất trong tối đa khoảng 18 ms |
| p95 | 75 ms | 95% request hoàn tất trong tối đa khoảng 75 ms |
| p99 | 210 ms | 99% request hoàn tất trong tối đa khoảng 210 ms |

Trong ví dụ này, khoảng 1% request chậm hơn 210 ms. p99 không có nghĩa mọi request đều hoàn tất trong 210 ms; vẫn có thể tồn tại outlier rất chậm.

### 2.1. Vì sao cần cả ba percentile?

p50 phản ánh trải nghiệm điển hình và thường ít bị ảnh hưởng bởi một số outlier. p95 thể hiện phần đuôi chậm có ảnh hưởng tới nhiều người dùng hơn. p99 giúp nhìn thấy tail latency do queueing, lock contention, garbage collection, network retry, connection pool exhaustion hoặc dependency chậm.

Nếu chỉ nhìn p50, một hệ thống có thể trông rất nhanh trong khi 5% hoặc 1% request bị chậm nghiêm trọng. Nếu chỉ nhìn p99, ta có thể bỏ qua việc phần lớn request đã chậm lên đáng kể. Cả ba chỉ số cần được đọc cùng throughput, error rate và thời gian phục hồi.

### 2.2. Ví dụ phân bố latency

Giả sử 10.000 request có phân bố như sau:

| Khoảng latency | Số request |
|---|---:|
| Dưới 20 ms | 5.000 |
| 20–50 ms | 4.000 |
| 50–100 ms | 900 |
| 100–250 ms | 90 |
| Trên 250 ms | 10 |

p50 nằm gần ranh giới 20 ms; p95 nằm gần vùng 50 ms; p99 nằm gần vùng 100 ms. Giá trị chính xác phụ thuộc latency từng mẫu và thuật toán percentile, không thể suy ra chính xác chỉ từ bảng bucket thô.

### 2.3. Percentile không thể cộng hoặc lấy trung bình để gộp

Không lấy trung bình p99 của các replica để tạo p99 toàn cụm. Ví dụ, replica A có 1.000 request với p99 20 ms, replica B có 10.000 request với p99 200 ms. Trung bình hai p99 là 110 ms nhưng không phải p99 của toàn bộ 11.000 request.

Muốn tính percentile toàn cụm, cần gộp histogram/bucket hoặc gộp raw samples từ các replica trong cùng cửa sổ và cùng định nghĩa metric. Với Prometheus histogram, có thể cộng rate của bucket theo label le rồi dùng histogram_quantile. Với client-side percentile đã được tính riêng ở từng process, không thể khôi phục phân bố gốc để gộp chính xác.

### 2.4. Sample size và độ tin cậy của p99

Percentile ở phần đuôi cần đủ số mẫu. Nếu chỉ có 100 request, p99 gần như phụ thuộc vào một request chậm nhất. Với 1.000 request, 1% tail tương đương khoảng 10 mẫu. Với 10.000 request, có khoảng 100 mẫu trong phần 1% tail.

Một quy tắc thực hành là thu thập ít nhất hàng chục nghìn mẫu cho mỗi nhóm traffic quan trọng khi muốn so sánh p99 ổn định; số lượng cần thiết còn phụ thuộc độ biến thiên và mức chênh lệch muốn phát hiện. Đây là heuristic, không phải bảo đảm thống kê. Với phép đo quan trọng, hãy lặp lại nhiều lượt độc lập và ước lượng khoảng tin cậy bằng bootstrap hoặc phương pháp thống kê phù hợp.

Không so sánh p99 của một lượt có 200 request với p99 của lượt có 200.000 request rồi kết luận một bản build nhanh hơn chỉ từ một con số.

## 3. Xác định ranh giới đo latency

Độ trễ phụ thuộc điểm bắt đầu và kết thúc. Trước khi thu thập số liệu, hãy thống nhất ranh giới đo.

### 3.1. Client-side end-to-end latency

Client-side latency đo từ lúc load generator bắt đầu gửi request tới khi nhận đủ response. Nó bao gồm:

- Thời gian chờ ở load generator.
- DNS lookup nếu client phải phân giải.
- Kết nối TCP và TLS nếu chưa tái sử dụng connection.
- Network round trip.
- Queueing tại proxy/load balancer.
- Thời gian xử lý phía server.
- Thời gian serialize response và truyền dữ liệu về client.

Đây là góc nhìn gần với trải nghiệm người dùng nhất, nhưng cần bảo đảm load generator không bị quá tải và đồng hồ đo không bị sai lệch.

### 3.2. Server-side processing latency

Server-side latency đo thời gian từ khi request được server nhận hoặc đưa vào handler tới khi handler hoàn tất. Metric này hữu ích để tách vấn đề bên trong ứng dụng khỏi network và load balancer.

Nếu server-side p99 thấp nhưng client-side p99 cao, hãy kiểm tra queueing ở proxy, network, client, connection setup hoặc load generator. Nếu cả hai cùng cao, nguyên nhân có thể nằm trong application, dependency hoặc tài nguyên máy.

### 3.3. Queueing latency

Một request có thể chờ trong accept queue, event loop, executor hoặc thread pool trước khi handler bắt đầu. Nếu chỉ đo thời gian bên trong handler, queueing latency có thể bị bỏ qua.

Khi tải vượt khả năng xử lý, queueing thường làm p95/p99 tăng rất nhanh. Hãy đo thời điểm nhận request, thời điểm bắt đầu xử lý và thời điểm hoàn tất nếu framework cho phép.

### 3.4. Dùng monotonic clock

Để đo duration trong JVM, dùng đồng hồ monotonic như System.nanoTime(), không dùng System.currentTimeMillis() để trừ hai timestamp. Wall clock có thể bị điều chỉnh bởi NTP hoặc thao tác hệ thống; monotonic clock phù hợp để đo khoảng thời gian.

Ví dụ:

~~~java
long started = System.nanoTime();
try {
    handleRequest();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    requestTimer.record(elapsedNanos, TimeUnit.NANOSECONDS);
}
~~~

Không trộn duration tính bằng nanosecond, microsecond và millisecond mà không chuyển đổi đơn vị. Khi lưu histogram, hãy giữ một đơn vị thống nhất và ghi rõ đơn vị trong tên metric hoặc metadata.

## 4. Thiết kế phép đo riêng cho CRaC restore

Một báo cáo hiệu năng sau restore nên chia thành nhiều pha để không che mất trải nghiệm ngay sau khi phục hồi.

### 4.1. Các mốc thời gian

Ghi nhận tối thiểu:

| Mốc | Ý nghĩa |
|---|---|
| T0 | Bắt đầu lệnh/API restore |
| T1 | Runtime hoàn tất restore và ứng dụng tiếp tục thực thi |
| T2 | Các callback afterRestore bắt đầu/kết thúc |
| T3 | Dependency bắt buộc đã được kiểm tra |
| T4 | Readiness mở |
| T5 | Request đầu tiên được gửi |
| T6 | Request đầu tiên hoàn tất |
| T7 | Bắt đầu cửa sổ steady-state |
| T8 | Kết thúc cửa sổ đo |

Từ các mốc này có thể tính:

\[
T_{restore} = T1 - T0
\]

\[
T_{restore\_to\_ready} = T4 - T1
\]

\[
T_{first\_request} = T6 - T5
\]

\[
T_{restore\_to\_first\_success} = T6 - T1
\]

Hãy ghi rõ cách xác định T1. Một số engine không cung cấp callback công khai đúng thời điểm runtime restore kết thúc; khi đó dùng mốc gần nhất có thể quan sát và đặt tên metric chính xác, ví dụ process-resumed-to-ready.

### 4.2. Chia cửa sổ đo

Nên báo cáo riêng ít nhất ba cửa sổ:

1. **First-request window:** request đầu tiên và nhóm request ngay sau readiness.
2. **Warm-up window:** giai đoạn ứng dụng tăng dần cache, connection và khả năng xử lý.
3. **Steady-state window:** giai đoạn đạt điều kiện ổn định và chạy tải đo chính.

Ví dụ một lần chạy có thể dùng 100 request đầu tiên cho first-request window, 2 phút tiếp theo làm warm-up và 10 phút sau đó làm steady-state. Các con số này chỉ là ví dụ; chọn theo workload và SLO thực tế.

Không bỏ first-request window khỏi báo cáo. Nếu dịch vụ nhận traffic ngay sau readiness, latency của nhóm request đầu tiên là một phần trải nghiệm production.

### 4.3. Đo trước và sau readiness

Nếu gửi request trước readiness, mục tiêu là kiểm tra routing và khả năng từ chối request khi instance chưa sẵn sàng. Không trộn các response 503 hoặc timeout trong giai đoạn này với latency của request nghiệp vụ sau readiness.

Hãy ghi riêng:

- Thời điểm readiness đóng.
- Thời điểm readiness mở.
- Request bị từ chối trước readiness.
- Request đầu tiên được routing sau readiness.
- Thời gian từ restore tới request thành công đầu tiên.

Đừng loại response lỗi khỏi báo cáo tổng thể. Có thể loại chúng khỏi latency phân bố của request thành công nếu định nghĩa rõ, nhưng phải báo error rate và số lỗi riêng để tránh làm đẹp số liệu.

### 4.4. So sánh với cold start và warm restart

Để biết CRaC cải thiện điều gì, nên có ít nhất ba baseline:

- **Cold start:** chạy JVM bình thường, không restore checkpoint.
- **CRaC restore:** khôi phục từ checkpoint image.
- **Warm restart hoặc steady instance:** instance đã chạy ổn định, dùng làm mốc tham khảo cho latency khi không có tác động startup.

So sánh cả restore-to-ready và request latency. CRaC có thể giảm thời gian tới readiness nhưng p99 sau restore vẫn tăng nếu connection pool, cache hoặc credential chưa phục hồi đúng.

## 5. Đo latency và throughput trong cùng một phép thử

Latency và throughput cần được đo trong cùng cửa sổ tải để hiểu quan hệ giữa chúng.

### 5.1. Offered load và achieved throughput

Offered load là tốc độ load generator cố gắng gửi request. Achieved throughput là tốc độ request thực sự hoàn tất.

Ví dụ:

- Load generator dự định gửi 1.000 request/giây.
- Ứng dụng hoàn tất 850 request/giây.
- 100 request/giây bị timeout.
- 50 request/giây bị bỏ lỡ hoặc không được tạo do generator quá tải.

Chỉ ghi “850 RPS” là chưa đủ. Báo cáo cần thể hiện offered rate, completed rate, success rate, error rate và dropped iterations.

### 5.2. Throughput theo cửa sổ thời gian

Nếu có N request hoàn tất trong cửa sổ đo dài W giây:

\[
Throughput = \frac{N}{W}
\]

Ví dụ 60.000 request hoàn tất trong 60 giây tương ứng 1.000 completed requests/second.

Nếu chỉ tính request thành công:

\[
Goodput = \frac{N_{success}}{W}
\]

Hãy dùng cùng một định nghĩa ở tất cả baseline. Không so completed throughput của một lần chạy với successful throughput của lần chạy khác.

### 5.3. Throughput theo replica và toàn cụm

Ghi nhận:

- RPS của từng replica.
- Tổng RPS của cụm.
- RPS thành công.
- RPS lỗi.
- Số request đang in-flight.
- Queue depth và số request bị từ chối.

Tổng throughput có thể tăng trong khi một replica bị quá tải hoặc không nhận được traffic. Theo dõi phân bố request giữa replica để phát hiện load imbalance.

### 5.4. Throughput không thể đọc riêng lẻ

Một hệ thống có thể tăng RPS bằng cách tăng concurrency nhưng làm p99 tăng mạnh. Khi server bão hòa, queue dài hơn và request chờ lâu hơn. Do đó, mỗi điểm tải cần có bộ số liệu:

- Offered RPS.
- Successful RPS.
- p50, p95, p99.
- Error/timeout rate.
- CPU, memory, GC và thread/connection pool.
- Queue depth hoặc in-flight requests.

Điểm tải phù hợp thường nằm dưới vùng bão hòa và đáp ứng SLO latency/error rate.

## 6. Chọn mô hình tải: open-loop và closed-loop

Mô hình tải ảnh hưởng trực tiếp đến latency được đo.

### 6.1. Closed-loop load

Trong closed-loop, một virtual user gửi request tiếp theo sau khi request trước hoàn tất. Khi server chậm, tốc độ gửi tự giảm. Mô hình này phù hợp để mô phỏng người dùng chờ response rồi mới thao tác tiếp.

Nhược điểm là khi server quá tải, load generator cũng tự giảm offered rate. Kết quả có thể không phản ánh được độ trễ mà một luồng request liên tục sẽ gặp.

### 6.2. Open-loop load

Trong open-loop, load generator phát request theo lịch độc lập với thời gian response. Ví dụ cố định 500 request/giây dù server đang trả chậm.

Mô hình này phù hợp để đo hệ thống dưới một arrival rate xác định và phát hiện queueing. Tuy nhiên, nếu generator không đủ tài nguyên, request có thể bị trễ ngay trong generator hoặc bị drop. Cần theo dõi dropped iterations và khả năng phát request đúng lịch.

### 6.3. Coordinated omission

Coordinated omission xảy ra khi load generator chỉ tạo request mới sau khi request trước hoàn tất. Khi server bị stall, generator cũng ngừng gửi; các request lẽ ra phải được gửi trong thời gian stall không xuất hiện trong mẫu latency. Kết quả percentile có thể trông tốt hơn thực tế.

Để giảm sai lệch:

- Dùng open-loop arrival rate khi cần mô phỏng traffic liên tục.
- Chọn công cụ có cách ghi nhận latency theo lịch gửi hoặc hỗ trợ correction phù hợp.
- Báo dropped/late iterations.
- Kiểm tra generator không bị CPU/network bottleneck.
- Nếu dùng closed-loop, ghi rõ đây là workload user-driven và không diễn giải nó như open-loop service capacity.

Không chỉ bật một tùy chọn correction rồi coi mọi sai lệch đã được giải quyết. Hãy đọc tài liệu của công cụ và xác nhận cách nó tính latency.

## 7. Instrumentation trong ứng dụng Java

Có thể thu thập latency bằng Micrometer Timer, OpenTelemetry Histogram hoặc thư viện histogram như HdrHistogram. Mục tiêu là lưu đủ thông tin để tính percentile theo cửa sổ và theo nhóm request.

### 7.1. Dùng Micrometer Timer

Ví dụ với Micrometer:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

public final class RequestMetrics {
    private final Timer requestTimer;

    public RequestMetrics(MeterRegistry registry) {
        this.requestTimer = Timer.builder("orders.request.duration")
                .description("Thoi gian xu ly request Orders")
                .tag("operation", "create-order")
                .publishPercentileHistogram()
                .register(registry);
    }

    public void record(long startedNanos) {
        long elapsed = System.nanoTime() - startedNanos;
        requestTimer.record(elapsed, TimeUnit.NANOSECONDS);
    }
}
~~~

Ví dụ trên tạo histogram để backend như Prometheus có thể tính percentile trên các bucket. Cấu hình bucket và SLA boundary nên phù hợp với dải latency của dịch vụ. Không bật mọi tag có giá trị vô hạn như user ID, order ID hoặc request ID vì sẽ làm tăng cardinality.

### 7.2. Client-side percentile và histogram

Micrometer có thể publish percentile đã tính tại từng process bằng cấu hình percentile, nhưng các giá trị percentile riêng lẻ không thể cộng để tạo percentile toàn cụm. Khi cần gộp dữ liệu từ nhiều replica, ưu tiên histogram/bucket có thể tổng hợp.

Phân biệt:

- Client-side percentile: tính tại một instance; hữu ích khi xem từng replica.
- Histogram bucket: đếm số quan sát theo bucket; có thể gộp qua nhiều replica nếu cùng cấu hình bucket.
- Raw samples: cho phép tính percentile linh hoạt nhất nhưng có chi phí lưu trữ và truyền dữ liệu cao.

### 7.3. OpenTelemetry Histogram

Với OpenTelemetry, có thể ghi duration bằng Histogram instrument. Hãy dùng unit nhất quán, ví dụ seconds, và đặt attributes có cardinality hữu hạn như route template, method, status class hoặc operation type.

Không dùng URL đầy đủ chứa ID động làm attribute. Thay bằng route template như /orders/{id}. Khi xuất dữ liệu, xác nhận backend hỗ trợ histogram aggregation và percentile theo cửa sổ.

### 7.4. Đo ở cả client và server

Nên có ít nhất hai lớp metric:

- Client-side end-to-end duration để phản ánh trải nghiệm và queue/network.
- Server-side handler duration để phân tích phần xử lý bên trong ứng dụng.

Nếu có proxy hoặc gateway, có thể thu thêm upstream duration và queue duration. Đảm bảo metric names và boundaries rõ ràng để không so sánh các đại lượng khác định nghĩa.

## 8. Tính p50, p95, p99 với Prometheus histogram

Với Micrometer Prometheus registry và histogram bucket, có thể dùng PromQL:

~~~promql
histogram_quantile(
  0.50,
  sum by (le) (
    rate(orders_request_duration_seconds_bucket[5m])
  )
)
~~~

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(orders_request_duration_seconds_bucket[5m])
  )
)
~~~

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(orders_request_duration_seconds_bucket[5m])
  )
)
~~~

Đây là ví dụ tính percentile toàn cụm bằng cách gộp bucket của các replica. Nếu muốn xem từng instance, giữ thêm label instance trong phép sum:

~~~promql
histogram_quantile(
  0.99,
  sum by (instance, le) (
    rate(orders_request_duration_seconds_bucket[5m])
  )
)
~~~

Tên metric thực tế phụ thuộc naming convention và registry. Kiểm tra endpoint metrics để xác nhận đúng tên và đơn vị. Histogram quantile là phép ước lượng dựa trên bucket; độ chính xác phụ thuộc bucket boundaries và phân bố quan sát.

### 8.1. Đo throughput bằng counter

Nếu Timer xuất count:

~~~promql
sum(rate(orders_request_duration_seconds_count[1m]))
~~~

Kết quả là completed observations mỗi giây nếu Timer được ghi đúng một lần cho mỗi request hoàn tất.

Để chỉ tính request thành công, cần metric có tag outcome/status hoặc counter riêng. Ví dụ:

~~~promql
sum(
  rate(http_server_requests_seconds_count{status=~"2.."}[1m])
)
~~~

Tên label status phụ thuộc instrumentation. Hãy xác nhận label thực tế và định nghĩa “thành công” theo hợp đồng API; một số hệ thống xem 3xx hoặc response nghiệp vụ đặc biệt là thành công.

### 8.2. Error rate

Ví dụ tỷ lệ response 5xx:

~~~promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
~~~

Timeout phía client có thể không xuất hiện như 5xx server. Hãy đo thêm timeout và dropped request từ load generator. Không kết luận error rate bằng 0 chỉ vì server không ghi nhận 5xx.

### 8.3. Không gộp percentile đã tính sẵn

Không dùng phép tính kiểu:

~~~promql
avg by (cluster) (instance_request_p99)
~~~

để đại diện p99 toàn cụm. Hãy gộp histogram bucket trước rồi tính quantile như các ví dụ trên. Nếu chỉ có summary/client-side percentile mà không có histogram, hãy báo percentile từng replica hoặc thu raw samples ở hệ thống đo.

## 9. Dùng load generator để đo sau restore

Có thể dùng k6, Gatling, wrk2 hoặc công cụ tương đương. Chọn công cụ dựa trên workload và cách tạo tải:

- HTTP API: k6, Gatling, wrk2.
- gRPC: công cụ có hỗ trợ protocol và concurrency tương ứng.
- Message consumer: producer/consumer load harness đo processing rate và end-to-end event latency.
- Microbenchmark method/JVM: JMH; không dùng JMH để thay thế benchmark service qua network.

### 9.1. Ví dụ k6 với arrival rate cố định

Script minh họa:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    restored_service: {
      executor: 'constant-arrival-rate',
      rate: 300,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 50,
      maxVUs: 300,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: [
      'p(95)<150',
      'p(99)<300',
    ],
  },
};

export default function () {
  const response = http.get(
    'http://service-under-test/health/business'
  );
  check(response, {
    'status is successful': (r) => r.status === 200,
  });
}
~~~

Đây là ví dụ kiểm tra endpoint đơn giản. Trong benchmark thật, hãy dùng endpoint đại diện cho workload, payload thực tế và dữ liệu kiểm thử phù hợp. Không dùng health endpoint nhẹ để đại diện cho luồng tạo đơn hàng có database và broker.

Với k6, các Trend metrics như http_req_duration có thể hiển thị p50, p95 và p99 trong summary. Hãy lưu summary JSON hoặc output time-series để so sánh giữa các lần chạy. Theo dõi dropped_iterations, VUs và lỗi generator; nếu generator không phát đủ arrival rate, kết quả không đại diện cho tải dự định.

### 9.2. Tách first-request và steady-state scenario

Không nên dùng một script duy nhất rồi trộn mọi request vào cùng một percentile nếu mục tiêu là so sánh các pha. Có thể gắn tag phase:

- first_request
- warmup
- steady_state

Hoặc chạy các scenario riêng và lưu output theo tên phase. Đảm bảo first-request test thật sự bắt đầu sau readiness của replica, còn steady-state test bắt đầu sau khi điều kiện warm-up được thỏa mãn.

### 9.3. Test nhiều replica

Trong môi trường multi-replica:

- Gửi traffic qua load balancer để đo trải nghiệm cụm.
- Gửi traffic trực tiếp từng replica để đo độ lệch giữa instance.
- Giữ cùng workload và arrival rate khi so sánh baseline.
- Ghi số replica thực sự ready trong suốt cửa sổ đo.
- Theo dõi load balancing và số request mỗi replica nhận.

Nếu một replica vừa restore trong khi các replica khác đã ổn định, đo riêng latency của replica mới và latency toàn cụm. Hai số này trả lời hai câu hỏi khác nhau.

## 10. Xây dựng workload đại diện

Một benchmark chỉ có ý nghĩa khi workload phản ánh hành vi thực tế.

### 10.1. Chọn request mix

Xác định tỷ trọng của:

- Request đọc cache.
- Request đọc database.
- Request ghi database.
- Request gọi dịch vụ ngoài.
- Request có payload lớn.
- Request có xử lý CPU cao.
- Request có nhiều bước nghiệp vụ.

Không benchmark một endpoint tĩnh rồi suy ra toàn bộ ứng dụng nhanh hơn. CRaC có thể cải thiện startup nhưng không thay đổi chi phí của query hoặc external API.

### 10.2. Payload và dữ liệu

Giữ payload size, phân bố dữ liệu và mức cache hit nhất quán giữa các lần chạy. Nếu dataset quá nhỏ và nằm hoàn toàn trong cache, kết quả có thể không đại diện production. Nếu mỗi lượt chạy dùng dữ liệu khác nhau, khác biệt có thể đến từ data locality thay vì restore.

### 10.3. Concurrency và arrival rate

Chạy nhiều điểm tải:

- Tải thấp để đo latency nền.
- Tải trung bình gần mức thường dùng.
- Tải cao gần saturation.
- Tải vượt capacity để xác định cách hệ thống suy giảm.

Ở mỗi điểm tải, ghi latency, throughput, errors, CPU và queue. Không so p99 ở 100 RPS với p99 ở 2.000 RPS rồi quy toàn bộ khác biệt cho CRaC.

### 10.4. Giữ dependency nhất quán

Database, broker, cache, API bên ngoài và network phải có cấu hình giống nhau giữa các lượt so sánh. Nếu dependency bị restart hoặc có tải cạnh tranh khác nhau, latency sau restore sẽ bị ảnh hưởng.

Với một test đặc biệt về dependency recovery, hãy cố ý thay đổi dependency trong thời gian dừng và báo đó là fault scenario riêng. Không trộn fault scenario với benchmark baseline.

## 11. Quy trình benchmark đề xuất

Một lượt benchmark có thể chia thành các bước sau.

### Bước 1: Ghi nhận môi trường

Lưu:

- JDK vendor, version, build và CRaC engine.
- Ứng dụng version, commit và checkpoint image digest.
- CPU model, số core, memory và kernel.
- Container limits, cgroup CPU/memory quota.
- Runtime, orchestration và node type.
- Database, broker, cache và dependency version.
- JVM flags, GC, heap size và cấu hình thread/connection pool.
- Network topology và load generator version.

### Bước 2: Tạo checkpoint

1. Khởi động ứng dụng.
2. Chạy warm-up theo quy trình đã định.
3. Xác nhận trạng thái ứng dụng phù hợp để checkpoint.
4. Tạo checkpoint image.
5. Ghi digest và log.

### Bước 3: Restore và chờ readiness

1. Restore từ ảnh chuẩn.
2. Ghi thời điểm runtime resume.
3. Ghi callback afterRestore và thời gian tạo lại resource.
4. Xác nhận dependency health.
5. Ghi thời điểm readiness mở.

### Bước 4: Đo first-request

Gửi một cửa sổ request nhỏ ngay sau readiness. Lưu latency từng request hoặc histogram riêng, response status, lỗi và timeout. Ghi rõ có tái sử dụng connection hay không.

### Bước 5: Đo warm-up

Chạy workload warm-up theo policy production. Theo dõi cache hit, pool size, CPU, GC và latency theo từng cửa sổ. Đánh dấu thời điểm ứng dụng đạt điều kiện steady-state.

### Bước 6: Đo steady-state

Chạy workload ở các mức arrival rate định trước trong cửa sổ đủ dài. Thu thập p50, p95, p99, throughput thành công, error rate, dropped iterations, CPU, memory, GC và queue depth.

### Bước 7: Lặp lại

Lặp nhiều lượt độc lập. Nếu có thể, xen kẽ thứ tự baseline cold start và CRaC restore để giảm ảnh hưởng của thay đổi tải hệ thống hoặc thời điểm chạy.

### Bước 8: Tổng hợp

Tính percentile theo từng pha, từng endpoint và toàn cụm. So sánh cùng một định nghĩa, cùng tải và cùng cửa sổ. Báo sample count và khoảng tin cậy khi cần.

## 12. So sánh baseline và tính mức cải thiện

Để so sánh CRaC với cold start, cần giữ nguyên workload và môi trường.

### 12.1. Bảng so sánh mẫu

| Chỉ số | Cold start | CRaC restore | Mức thay đổi |
|---|---:|---:|---:|
| Restore/start-to-ready | 8,2 s | 1,4 s | Giảm 82,9% |
| First-request p50 | 24 ms | 20 ms | Giảm 16,7% |
| First-request p95 | 110 ms | 95 ms | Giảm 13,6% |
| First-request p99 | 340 ms | 290 ms | Giảm 14,7% |
| Steady-state p50 | 14 ms | 14 ms | Không đổi |
| Steady-state p95 | 48 ms | 49 ms | Tăng 2,1% |
| Steady-state p99 | 130 ms | 135 ms | Tăng 3,8% |
| Successful throughput | 900 RPS | 895 RPS | Giảm 0,6% |

Các số trong bảng chỉ là dữ liệu minh họa. Chúng cho thấy CRaC có thể cải thiện thời gian sẵn sàng và first-request trong khi steady-state gần như không thay đổi. Cũng có thể xảy ra trường hợp restore-to-ready giảm mạnh nhưng p99 tăng do callback tạo kết nối đồng loạt hoặc cache chưa warm-up.

### 12.2. Tính phần trăm cải thiện

Với một metric mà giá trị thấp hơn là tốt hơn, phần trăm giảm:

\[
Improvement(\%) =
\frac{Baseline - New}{Baseline} \times 100
\]

Với throughput, giá trị cao hơn thường tốt hơn:

\[
ThroughputGain(\%) =
\frac{New - Baseline}{Baseline} \times 100
\]

Không dùng cùng công thức cho mọi metric. Với error rate, dropped iterations và resource usage, hãy xác định rõ chiều tốt/xấu và SLO.

### 12.3. Đọc kết quả theo từng pha

Nếu restore-to-ready giảm nhưng first-request p99 tăng, có thể ứng dụng mở readiness trước khi connection pool hoặc cache thực sự sẵn sàng. Nếu first-request tốt nhưng steady-state throughput giảm, kiểm tra resource limit, pool size, GC, CPU quota và load balancing.

Nếu p50 cải thiện nhưng p99 xấu đi, có thể phần lớn request được phục vụ nhanh hơn nhưng một nhóm nhỏ bị ảnh hưởng bởi connection creation, lock, GC hoặc dependency retry. Hãy phân tích histogram và trace của request chậm thay vì chỉ xem một percentile.

## 13. Phân tích tail latency sau restore

Tail latency thường là nơi phát hiện vấn đề mà p50 che giấu.

### 13.1. Connection pool tạo lại đồng loạt

Sau restore, nhiều request có thể cùng kích hoạt tạo connection. Nếu database giới hạn số connection, một số request phải chờ pool hoặc handshake. Theo dõi:

- Active/idle/pending connections.
- Connection creation duration.
- Pool acquire latency.
- Database connection limit và server load.
- Error/timeout khi pool chưa sẵn sàng.

Có thể warm-up một số connection trước readiness nếu chính sách cho phép, nhưng phải tránh mở quá nhiều kết nối cùng lúc trên toàn cụm.

### 13.2. Cache miss sau restore

Cache có thể được snapshot với dữ liệu cũ hoặc bị invalidation. Nếu nhiều replica cùng tải lại cache sau restore, nguồn dữ liệu có thể bị dồn tải.

Theo dõi cache hit ratio, load duration, refresh count và request latency theo cache state. Nếu cache được nạp bất đồng bộ, readiness cần phản ánh liệu cache đó có bắt buộc cho chức năng phục vụ hay không.

### 13.3. Garbage collection và memory pressure

Restore có thể đưa heap vào trạng thái khác với cold start. Khi tải tăng, allocation burst hoặc cache refresh có thể gây GC pause và làm p99 tăng.

Theo dõi:

- GC pause duration và frequency.
- Allocation rate.
- Heap occupancy.
- Old generation pressure.
- CPU throttling.
- Container memory limit và OOM events.

Không kết luận GC là nguyên nhân chỉ vì p99 tăng cùng thời điểm GC. Dùng GC log, JFR hoặc telemetry để tương quan với request chậm.

### 13.4. JIT và class loading

Một số đường code có thể chưa được thực thi trước checkpoint hoặc cần tiếp tục tối ưu sau restore. Request đầu tiên có thể kích hoạt class loading, initialization hoặc compilation. Đo latency theo request count/time sau readiness để biết hiệu ứng này có giảm dần không.

Không gộp request đầu tiên với steady-state nếu mục tiêu là hiểu warm-up. Ngược lại, nếu production nhận traffic ngay sau readiness, không được bỏ qua first-request latency trong SLO.

### 13.5. Dependency recovery và retry storm

Nếu nhiều replica restore đồng thời, chúng có thể cùng lấy token, mở connection, join broker group hoặc tải cache. Dependency bị quá tải sẽ tạo tail latency và retry storm.

Thử restore theo batch và theo đợt lệch thời gian. Theo dõi rate tới dependency, lỗi, retry và thời gian readiness. Jitter/backoff và giới hạn concurrency có thể giảm tải phục hồi.

## 14. Kiểm soát sai số và tính lặp lại

Benchmark có thể bị ảnh hưởng bởi CPU frequency, background load, GC, cache filesystem, network, database load và chính load generator.

### 14.1. Kiểm soát môi trường

- Dùng cùng loại node, CPU quota và memory limit.
- Giữ JDK, GC, JVM flags và dependency version giống nhau.
- Dùng cùng checkpoint image digest cho các lượt restore cần so sánh.
- Giữ database, broker và cache ở trạng thái tương đương.
- Đảm bảo load generator không chạy trên cùng CPU bị bão hòa với service nếu điều đó làm méo kết quả.
- Ghi nhận CPU throttling, noisy neighbor và network congestion.

### 14.2. Lặp lại độc lập

Chạy nhiều lượt độc lập cho cold start và CRaC restore. Mỗi lượt nên có checkpoint/restore lifecycle riêng, không lấy nhiều cửa sổ từ cùng một process rồi coi đó là nhiều trial độc lập.

Tổng hợp:

- Median của các trial-level p50/p95/p99.
- Phạm vi min/max hoặc khoảng tin cậy.
- Sample count mỗi trial.
- Throughput trung bình và độ biến thiên.
- Error rate và số lần dropped.

Không chỉ báo trial tốt nhất. Nếu các trial dao động lớn, cần tìm nguyên nhân trước khi kết luận.

### 14.3. Bootstrap confidence interval

Khi có raw latency samples, có thể dùng bootstrap để ước lượng khoảng tin cậy của p95/p99:

1. Lấy mẫu ngẫu nhiên có hoàn lại từ tập request latency.
2. Tính percentile cho mẫu bootstrap.
3. Lặp lại nhiều lần.
4. Lấy các quantile của tập percentile bootstrap làm khoảng tin cậy.

Với dữ liệu có tương quan theo thời gian, việc lấy mẫu độc lập từng request có thể đánh giá thấp biến thiên. Có thể cần block bootstrap hoặc phân tích theo trial/window để giữ cấu trúc thời gian.

### 14.4. Đồng hồ và timestamp giữa máy

Không trừ timestamp wall-clock từ hai máy nếu chưa kiểm soát clock synchronization. Để đo end-to-end, ưu tiên thời gian do một load generator duy nhất đo từ lúc gửi tới lúc nhận response. Để tương quan trace giữa máy, dùng tracing system và clock synchronization, nhưng không dùng timestamp phân tán làm phép đo duration chính khi clock skew chưa được đánh giá.

## 15. Những lỗi đo lường thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ đo thời gian JVM restore | Bỏ qua thời gian bootstrap và readiness | Đo restore-to-ready và first-success riêng |
| Chỉ đo p50 | Che giấu tail latency | Báo p50, p95, p99 cùng error rate |
| Lấy trung bình p99 của các replica | Không tạo ra p99 toàn cụm | Gộp histogram bucket hoặc raw samples |
| Dùng quá ít mẫu | p99 không ổn định | Tăng sample count và lặp nhiều trial |
| Không tách first-request với steady-state | Warm-up bị che trong một con số | Gắn phase và đo cửa sổ riêng |
| Chỉ tính request thành công | Bỏ qua timeout và lỗi | Báo success latency cùng error/timeout rate |
| Dùng closed-loop nhưng diễn giải như open-loop | Coordinated omission làm latency trông thấp | Chọn mô hình tải phù hợp và báo rõ |
| Load generator bị quá tải | Offered rate không đạt kế hoạch | Theo dõi dropped iterations và tài nguyên generator |
| Chỉ đo server handler | Bỏ qua queue/network/proxy | Đo thêm client-side end-to-end |
| Không cố định workload | So sánh không công bằng | Giữ request mix, payload, data và rate |
| Gộp các replica có số request rất khác nhau mà không weighted histogram | Percentile cụm sai | Gộp bucket count/rate đúng cách |
| Không ghi sample count | Khó đánh giá độ tin cậy | Lưu count và thời gian cửa sổ |
| Chỉ báo RPS tổng | Có thể gồm response lỗi | Báo completed RPS, successful RPS và error rate |
| Bỏ qua CPU throttling | Gán nhầm nguyên nhân cho CRaC | Ghi quota, throttling và node load |
| Dùng wall clock để đo duration trong JVM | Clock adjustment làm duration sai | Dùng System.nanoTime() |

## 16. Ví dụ dashboard theo dõi sau restore

Một dashboard hiệu năng sau restore có thể chia thành bốn nhóm.

### 16.1. Recovery timeline

- Restore duration.
- Restore-to-ready duration.
- Thời gian callback từng Resource.
- Thời gian tạo lại pool/client.
- Time to first successful request.

### 16.2. Latency

- p50, p95, p99 theo route/operation.
- Client-side end-to-end latency.
- Server-side handler latency.
- First-request window.
- Warm-up window.
- Steady-state window.

### 16.3. Throughput và độ tin cậy

- Offered RPS.
- Completed RPS.
- Successful RPS/goodput.
- Error và timeout rate.
- Dropped/late iterations.
- In-flight request và queue depth.

### 16.4. Tài nguyên và dependency

- CPU, memory, heap và GC.
- Connection pool active/idle/pending.
- Cache hit ratio.
- Database/broker latency.
- Retry count và circuit breaker state.
- CPU throttling và network error.

Các dashboard nên cho phép lọc theo service, replica, version, checkpoint image digest và test run. Tránh dùng request ID hoặc user ID làm label metric có cardinality cao.

## 17. Mẫu báo cáo benchmark

Một báo cáo nên ghi đầy đủ cấu hình để có thể lặp lại:

~~~text
Test run ID:
Ngày/giờ:
Ứng dụng version/commit:
Checkpoint image digest:
JDK vendor/version/build:
CRaC engine:
Kernel/container runtime:
Node CPU/memory:
Container CPU/memory limits:
JVM flags/GC:
Dependency versions:
Load generator/version:
Workload mix:
Offered arrival rate:
Concurrency:
Warm-up policy:
Steady-state condition:
Measurement window:
Sample count:

Recovery:
- Restore duration:
- Restore-to-ready:
- Time to first successful request:

First-request window:
- p50:
- p95:
- p99:
- successful throughput:
- error/timeout rate:

Warm-up window:
- p50:
- p95:
- p99:
- successful throughput:
- error/timeout rate:

Steady-state window:
- p50:
- p95:
- p99:
- completed throughput:
- successful throughput:
- error/timeout rate:
- dropped iterations:

Resources:
- CPU:
- memory/heap:
- GC pause:
- connection pool:
- cache hit ratio:
- queue depth:

Baseline:
- cold start:
- CRaC restore:
- số trial:
- khoảng tin cậy/độ biến thiên:

Kết luận:
- SLO đạt/không đạt:
- Khác biệt đáng chú ý:
- Hạn chế của phép đo:
~~~

Không chỉ lưu ảnh dashboard. Lưu raw result, histogram, load generator summary, log lifecycle và cấu hình để có thể kiểm tra lại cách tính percentile.

## 18. Acceptance criteria cho hiệu năng sau restore

Tiêu chí phải dựa trên SLO của ứng dụng. Ví dụ dưới đây là mẫu; hãy thay ngưỡng bằng số liệu phù hợp với workload.

**AC-01 — Readiness**

- Điều kiện: restore từ checkpoint image chuẩn.
- Kết quả: readiness mở trong ngưỡng restore-to-ready đã thống nhất.
- Bằng chứng: timestamp runtime resume, callback, dependency health và readiness transition.

**AC-02 — First-request latency**

- Điều kiện: gửi ít nhất N request ngay sau readiness.
- Kết quả: p50/p95/p99 nằm trong ngưỡng first-request SLO; lỗi và timeout được báo riêng.
- Bằng chứng: raw latency hoặc histogram có sample count.

**AC-03 — Steady-state latency**

- Điều kiện: ứng dụng đạt điều kiện warm-up và nhận offered load cố định.
- Kết quả: p50/p95/p99 đạt ngưỡng ở cửa sổ đo xác định.
- Bằng chứng: histogram, sample count, load generator rate và error rate.

**AC-04 — Throughput**

- Điều kiện: chạy workload với arrival rate định trước.
- Kết quả: successful throughput đạt mức tối thiểu trong khi error rate và tail latency vẫn trong SLO.
- Bằng chứng: completed/successful request count, dropped iterations và server metrics.

**AC-05 — Không có suy giảm bất thường giữa replica**

- Điều kiện: restore nhiều replica từ cùng image và phân phối traffic qua load balancer.
- Kết quả: không có replica có p99 hoặc error rate vượt ngưỡng mà không được giải thích.
- Bằng chứng: histogram theo instance, request distribution và resource metrics.

**AC-06 — So sánh công bằng với baseline**

- Điều kiện: cold start và CRaC restore dùng cùng workload, node class, dependency và load generator.
- Kết quả: báo cáo thể hiện restore-to-ready, first-request, steady-state p50/p95/p99 và goodput theo cùng định nghĩa.
- Bằng chứng: cấu hình, image digest, raw results và số trial.

Một benchmark chỉ được coi là đạt nếu cả latency, throughput và error rate thỏa điều kiện. Throughput cao với p99 vượt SLO hoặc error rate lớn không phải kết quả đạt yêu cầu.

## 19. Quy trình phân tích khi kết quả không đạt

Nếu p50, p95 hoặc p99 xấu hơn mục tiêu:

1. Xác nhận load generator đã phát đủ offered rate và không bị bão hòa.
2. Xác nhận sample count và measurement window đủ lớn.
3. So sánh client-side với server-side latency để xác định network/queue hay handler.
4. Xem histogram theo instance và route để tìm replica hoặc operation bất thường.
5. Tương quan request chậm với GC, CPU throttling, queue depth và pool acquire.
6. Kiểm tra callback afterRestore có thực hiện công việc nặng đồng bộ trước readiness không.
7. Kiểm tra cache warm-up, token refresh, connection creation và broker rebalance.
8. Kiểm tra retry storm hoặc dependency bị dồn tải khi nhiều replica restore đồng thời.
9. Lặp lại benchmark với một thay đổi tại một thời điểm để xác định nguyên nhân.

Nếu throughput thấp:

- Kiểm tra offered rate, dropped iterations và VU/concurrency.
- Kiểm tra CPU quota, memory pressure và GC.
- Kiểm tra thread pool, connection pool và queue capacity.
- Kiểm tra database/broker có phải bottleneck không.
- Kiểm tra load balancing có phân phối request đều không.
- Kiểm tra ứng dụng có đang trả lỗi nhanh thay vì hoàn tất nghiệp vụ không.

Không tối ưu chỉ dựa trên p99 nếu lỗi thực tế nằm ở throughput hoặc error rate. Một thay đổi có thể cải thiện percentile nhưng giảm goodput, hoặc ngược lại.

## 20. Nguyên tắc cần nhớ

- Tách restore duration, restore-to-ready, first-request, warm-up và steady-state latency.
- p50 mô tả phần giữa, p95 và p99 thể hiện tail latency; báo cả ba cùng sample count.
- Không lấy trung bình percentile của các replica để tạo percentile toàn cụm; gộp histogram bucket hoặc raw samples.
- Dùng monotonic clock như System.nanoTime() để đo duration trong JVM.
- Đo cả client-side end-to-end và server-side processing khi cần phân tích nguyên nhân.
- Báo offered rate, completed throughput, successful throughput, error rate và dropped iterations riêng.
- Chọn open-loop hoặc closed-loop theo mục tiêu; lưu ý coordinated omission.
- Tách first-request và warm-up khỏi steady-state nhưng không bỏ chúng khỏi báo cáo.
- Dùng histogram có bucket phù hợp để tính percentile có thể tổng hợp qua nhiều replica.
- Giữ workload, dependency, node, JDK, GC, container limit và load generator nhất quán giữa baseline.
- Lặp nhiều trial và báo biến thiên/khoảng tin cậy khi so sánh p95/p99.
- Chỉ kết luận CRaC cải thiện hiệu năng khi latency, throughput và error rate được đo theo cùng hợp đồng và SLO.

Đo p50, p95, p99 và thông lượng sau restore giúp xác định ứng dụng có phục hồi nhanh và phục vụ ổn định hay không. Khi tách rõ các pha recovery, first request, warm-up và steady-state, đồng thời kiểm soát mô hình tải và cách tổng hợp histogram, nhóm phát triển có thể đánh giá lợi ích CRaC bằng số liệu có thể lặp lại thay vì chỉ dựa vào cảm nhận rằng JVM đã khởi động nhanh hơn.
