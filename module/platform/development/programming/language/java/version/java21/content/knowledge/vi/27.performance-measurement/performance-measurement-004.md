# Mô hình hóa arrival rate, concurrency và thời gian chờ dependency

Khi đo hiệu năng một dịch vụ Java, ba đại lượng cần được xem cùng nhau là **arrival rate** (tốc độ request đến), **concurrency** (số request hoặc thao tác đang tồn tại đồng thời) và **thời gian chờ dependency** (thời gian request phải chờ tài nguyên hoặc dịch vụ khác). Chỉ nhìn throughput hoặc thời gian xử lý trung bình thường không đủ để giải thích vì sao latency tăng khi tải tăng.

Một dịch vụ có thể xử lý nhanh khi tải thấp nhưng chậm đột ngột khi queue, connection pool hoặc dependency đạt giới hạn. Mô hình hóa đúng các đại lượng giúp ước lượng số request in-flight, tìm điểm bão hòa và chọn giới hạn concurrency phù hợp. Các nguyên tắc dưới đây áp dụng cho Java 21, cả ứng dụng dùng platform thread lẫn virtual thread.

## 1. Phân biệt arrival rate, throughput và concurrency

Ba đại lượng này liên quan nhưng không thể dùng thay thế cho nhau:

| Đại lượng | Ý nghĩa | Đơn vị thường dùng |
|---|---|---|
| Offered arrival rate | Tốc độ request được gửi tới hệ thống trước khi admission control quyết định nhận hay từ chối | request/second (RPS) |
| Admitted arrival rate | Tốc độ request được hệ thống chấp nhận để xử lý | request/second |
| Throughput | Tốc độ request hoặc thao tác hoàn tất | request/second hoặc operation/second |
| Concurrency / in-flight | Số request hoặc thao tác đã bắt đầu nhưng chưa kết thúc tại một thời điểm | request hoặc operation |
| Latency / response time | Thời gian từ mốc bắt đầu đến mốc kết thúc đã định nghĩa | millisecond hoặc second |

Trong một hệ thống ổn định, nếu throughput đếm mọi request đã kết thúc (thành công, thất bại hoặc bị hủy), throughput thường tiến gần admitted arrival rate. Nếu metric chỉ đếm thành công, cần theo dõi riêng tỷ lệ lỗi và hủy. Khi hệ thống quá tải, offered arrival rate có thể cao hơn throughput; phần chênh lệch sẽ bị từ chối, bị drop hoặc tích tụ trong queue.

Ví dụ, gateway nhận 500 request/giây nhưng chỉ chấp nhận 350 request/giây. Nếu chỉ có 340 request/giây kết thúc trong cùng khoảng quan sát, chênh lệch 10 request/giây sẽ làm số request in-flight hoặc queue tăng nếu tình trạng kéo dài. Không thể dùng con số 500 RPS để tính concurrency của phần xử lý đã admission; cần dùng tốc độ request thực sự đi vào phạm vi đang đo.

## 2. Dùng Little's Law để tính concurrency trung bình

Little's Law mô tả mối quan hệ giữa số công việc trung bình trong một hệ thống ổn định, tốc độ công việc đi qua hệ thống và thời gian trung bình một công việc ở trong hệ thống:

\[
L = \lambda \times W
\]

Trong đó:

- `L`: số request hoặc operation trung bình đang ở trong phạm vi đo (concurrency trung bình).
- `λ` (lambda): arrival rate đi vào phạm vi đó, tính bằng request/operation mỗi giây.
- `W`: thời gian trung bình một request/operation ở trong phạm vi đó, tính bằng giây.

Ví dụ, dịch vụ chấp nhận trung bình 240 request/giây và thời gian từ lúc được nhận đến khi hoàn tất trung bình là 0,25 giây:

\[
L = 240 \times 0.25 = 60
\]

Trung bình có khoảng 60 request đang in-flight trong phạm vi này. Đây là số trung bình, không phải giới hạn concurrency cần cấu hình và cũng không có nghĩa mọi thời điểm đều có đúng 60 request.

### Phải dùng cùng một ranh giới đo

`λ` và `W` phải mô tả cùng một phạm vi. Nếu `λ` là số request được admission vào service thì `W` phải là thời gian từ lúc admission đến khi request rời service. Không lấy arrival rate toàn gateway nhân với thời gian xử lý riêng của database query.

Little's Law thường được áp dụng cho hệ thống ổn định trong một khoảng đo đủ dài với các giá trị trung bình hữu hạn. Nếu queue tăng liên tục vì tải đến lớn hơn khả năng xử lý, hệ thống chưa ở trạng thái ổn định; con số concurrency sẽ tiếp tục tăng và một phép tính từ trung bình ngắn hạn có thể gây hiểu nhầm.

## 3. Tính riêng từng giai đoạn của request

Một request thường đi qua nhiều giai đoạn: admission, chờ worker, xử lý CPU, chờ connection, gọi dependency, xử lý kết quả và trả response. Nên đo riêng mỗi giai đoạn để biết thời gian bị tiêu thụ ở đâu.

```text
Request đến
    |
    v
Admission / rate limit
    |
    v
Queue chờ worker
    |
    v
Xử lý trong ứng dụng
    |
    +------> Chờ connection / permit
    |                  |
    |                  v
    |             Gọi dependency
    |                  |
    |                  v
    |             Nhận kết quả
    |                  |
    +<-----------------+
    |
    v
Tạo response và hoàn tất
```

Ở mức khái quát:

\[
W_{request} = W_{admission} + W_{queue} + W_{application} + W_{dependency} + W_{response}
\]

Đây là cách phân rã theo các khoảng thời gian không chồng lấn. Nếu các dependency được gọi song song, thời gian request chờ nhóm dependency không bằng tổng thời gian từng lời gọi; thường nó gần với thời gian hoàn tất của nhánh chậm nhất cộng phần điều phối còn lại. Vì vậy, hãy đo bằng span hoặc timer theo đúng ranh giới, không cộng các số liệu có khoảng thời gian chồng lấn.

### Phân biệt thời gian chờ và thời gian phục vụ dependency

Một lời gọi dependency có thể gồm nhiều phần:

- Chờ lấy connection từ pool.
- Chờ semaphore hoặc giới hạn concurrency của client.
- Thiết lập kết nối nếu chưa tái sử dụng connection.
- Network round trip.
- Thời gian dependency xử lý request.
- Đọc và giải mã response.

Nếu timer bắt đầu trước khi lấy connection và kết thúc sau khi đọc response, nó đo tổng thời gian client quan sát được. Nếu muốn biết pool có đang là nút thắt hay không, cần đo riêng `connection acquisition wait` và `remote call duration`.

Không gọi toàn bộ thời gian đó là “thời gian server xử lý”. Client thường không thể tách chính xác thời gian network và thời gian xử lý nội bộ của server nếu dependency không cung cấp telemetry tương ứng.

## 4. Arrival rate tới dependency khác arrival rate tới service

Một request đầu vào có thể gọi một dependency nhiều lần, không gọi dependency nào hoặc gọi nhiều dependency song song. Vì vậy, arrival rate ở từng dependency cần được tính riêng.

Nếu mỗi request gọi dependency trung bình `k` lần và request được admission với tốc độ `λ_request`, arrival rate operation tới dependency xấp xỉ:

\[
\lambda_{dep} = \lambda_{request} \times E[k]
\]

Ví dụ, service nhận 200 request/giây. Mỗi request gọi inventory trung bình 1,2 lần (một số request cần kiểm tra thêm một lần). Khi đó:

\[
\lambda_{inventory} = 200 \times 1.2 = 240\ operations/second
\]

Nếu thời gian một operation inventory ở trong phạm vi đo trung bình 0,12 giây:

\[
L_{inventory} = 240 \times 0.12 = 28.8
\]

Tức trung bình có khoảng 29 operation inventory đang tồn tại đồng thời. Nếu đo thời gian từ lúc lấy connection tới khi trả connection, con số này có thể được dùng để ước lượng nhu cầu connection; nếu đo cả thời gian chờ pool, nó biểu diễn số operation đang chờ hoặc đang dùng pool trong phạm vi đó.

### Fan-out song song

Giả sử mỗi request gọi đồng thời ba dịch vụ: profile, pricing và inventory. Mỗi dependency nhận xấp xỉ một operation cho mỗi request, nhưng mỗi dependency có thời gian phản hồi và giới hạn riêng. Với 100 request/giây:

| Dependency | Arrival rate | Latency trung bình | Concurrency trung bình ước lượng |
|---|---:|---:|---:|
| Profile | 100 op/s | 40 ms | 4 |
| Pricing | 100 op/s | 180 ms | 18 |
| Inventory | 100 op/s | 90 ms | 9 |

Pricing có concurrency trung bình lớn nhất vì thời gian operation lâu nhất. Với một request đang gọi ba dependency song song, thời gian hoàn tất request bị chi phối nhiều bởi nhánh chậm, dù các nhánh khác đã trả kết quả.

Nếu một request gọi cùng dependency nhiều lần, dùng số lần gọi trung bình thực tế thay vì giả định luôn bằng một. Nếu chỉ một tỷ lệ request gọi dependency, có thể dùng xác suất đó trong `E[k]`.

## 5. Retry và hedging làm tăng arrival rate nội bộ

Retry không tạo thêm request từ người dùng, nhưng tạo thêm operation tới dependency. Nếu mỗi request có một lần gọi ban đầu và trung bình thêm `r` lần retry, số operation có thể tăng xấp xỉ theo hệ số `1 + r`.

Ví dụ, 200 request/giây gọi dependency một lần; trung bình 0,3 retry cho mỗi request:

\[
\lambda_{dep} \approx 200 \times (1 + 0.3) = 260\ operations/second
\]

Trong thực tế, retry thường tăng đúng vào lúc dependency chậm hoặc lỗi. Đây là thời điểm dependency ít khả năng tiếp nhận thêm tải nhất. Retry đồng loạt có thể tạo retry storm và làm hệ thống hồi phục chậm hơn.

Khi thiết kế retry:

- Đặt số lần retry tối đa và tổng deadline cho request.
- Dùng exponential backoff kèm jitter để phân tán lần thử lại.
- Chỉ retry lỗi tạm thời và thao tác có semantics retry an toàn; dùng idempotency key khi cần.
- Đặt retry budget hoặc giới hạn tỷ lệ retry so với request gốc.
- Ghi riêng số request gốc, số attempt và số operation thành công/thất bại.

Hedged request (gửi bản sao tới một replica khác khi request đầu chậm) cũng làm tăng operation arrival rate. Chỉ dùng khi lợi ích giảm tail latency lớn hơn chi phí tải bổ sung và có cơ chế hủy request thừa khi một nhánh đã thắng.

## 6. Mô hình hóa pool và mức sử dụng tài nguyên

Giả sử một dependency client có `m` connection hoặc slot hoạt động đồng thời. Nếu thời gian sử dụng slot trung bình là `S` giây, năng lực phục vụ lý thuyết của pool xấp xỉ:

\[
Capacity \approx \frac{m}{S}\ operations/second
\]

Ví dụ, pool có 24 connection và mỗi operation giữ connection trung bình 0,12 giây:

\[
Capacity \approx \frac{24}{0.12} = 200\ operations/second
\]

Nếu dependency nhận 240 operation/giây trong thời gian dài, arrival rate cao hơn năng lực lý thuyết của pool. Các operation phải chờ connection, bị timeout hoặc bị từ chối. Tăng số connection có thể giúp nếu database còn khả năng xử lý, nhưng cũng có thể làm database quá tải hơn.

Với một pool có `m` worker tương tự, service time trung bình `S` và arrival rate `λ`, mức sử dụng gần đúng là:

\[
\rho = \frac{\lambda \times S}{m}
\]

`ρ` là utilization ước lượng. Khi `ρ` tiến gần 1, hệ thống ít còn khoảng trống để hấp thụ burst hoặc biến động thời gian xử lý; queueing delay thường tăng nhanh. Nếu `ρ` lớn hơn hoặc bằng 1 trong thời gian dài, queue không thể ổn định nếu không có admission control, từ chối tải hoặc tăng năng lực phục vụ.

Đây là mô hình xấp xỉ cho pool đồng nhất, không phải dự báo chính xác cho mọi hệ thống. Service time có phân phối, worker có thể khác nhau, request có thể fan-out và dependency có giới hạn riêng. Dùng công thức để nhận diện nguy cơ, sau đó xác nhận bằng load test và số liệu thực tế.

## 7. Vì sao latency tăng mạnh gần điểm bão hòa?

Khi tải còn thấp, worker hoặc connection thường có thể nhận việc ngay. Khi utilization tăng cao, một request mới có xác suất phải chờ lớn hơn. Một biến động nhỏ của service time hoặc arrival rate có thể làm queue dài thêm.

Các dấu hiệu thường xuất hiện cùng nhau:

- Throughput tăng chậm hoặc chững lại dù offered arrival rate tiếp tục tăng.
- p95/p99 latency tăng nhanh hơn nhiều so với median.
- Queue depth và queue wait time tăng.
- Connection pool có nhiều waiter hoặc semaphore thường xuyên hết permit.
- Timeout, cancellation và retry tăng theo.
- CPU có thể cao, nhưng cũng có thể thấp nếu worker chủ yếu chờ dependency.

Không kết luận hệ thống còn capacity chỉ vì CPU chưa đạt 100%. Một ứng dụng có thể bị giới hạn bởi database connection, rate limit của API ngoài, lock contention, network hoặc queue admission trước khi CPU bão hòa.

## 8. Open workload và closed workload khi load test

Mô hình phát tải ảnh hưởng lớn đến kết luận về arrival rate và concurrency.

### Closed workload

Closed workload thường mô phỏng một số lượng client cố định. Mỗi client gửi request tiếp theo sau khi request trước hoàn tất, có thể cộng thêm think time.

Ví dụ: 100 virtual users, mỗi user chỉ có một request đang chờ. Khi server chậm, các user hoàn tất chậm hơn nên arrival rate tự giảm. Mô hình này hữu ích khi hệ thống thật có số client đồng thời bị giới hạn, nhưng có thể che giấu việc service không theo kịp một arrival rate bên ngoài cố định.

Nếu có `N` user hoạt động, response time trung bình `R` và think time trung bình `Z`, arrival rate xấp xỉ:

\[
\lambda \approx \frac{N}{R + Z}
\]

Khi `R` tăng, arrival rate do closed workload tạo ra tự giảm dù số user vẫn giữ nguyên. Đây là lý do mô hình closed không phù hợp để đại diện cho nguồn traffic bên ngoài tiếp tục gửi request theo một lịch cố định.

### Open workload

Open workload phát request theo lịch arrival độc lập với thời gian phản hồi trước đó, chẳng hạn 200 request/giây. Khi server chậm, request mới vẫn đến theo lịch; queue và concurrency tăng, cho thấy khả năng chịu tải và hành vi quá tải.

| Mô hình | Điều được giữ cố định | Hữu ích để đo |
|---|---|---|
| Closed | Số client/virtual user | Trải nghiệm nhóm client có số lượng hữu hạn |
| Open | Arrival rate hoặc lịch phát request | Khả năng xử lý lưu lượng đến độc lập với response time |

Nếu mục tiêu là xác định capacity theo RPS hoặc mô phỏng traffic API, open workload thường phù hợp hơn. Cần bảo đảm load generator đủ mạnh để tự nó không trở thành bottleneck.

### Tránh coordinated omission

Trong một số load test, generator chỉ gửi request mới sau khi request trước hoàn tất. Khi server bị chậm, generator cũng ngừng gửi, nên histogram latency có thể bỏ sót những request lẽ ra phải đến trong lúc hệ thống đang bận. Hiện tượng này thường được gọi là *coordinated omission*.

Để giảm sai lệch:

- Chọn open arrival model khi cần giữ tốc độ request độc lập với response.
- Ghi nhận cả request dự kiến gửi nhưng bị trễ do generator hoặc client không theo kịp.
- Dùng công cụ đo có hỗ trợ hiệu chỉnh coordinated omission nếu phù hợp.
- Theo dõi offered rate, admitted rate, completed throughput và rejected rate riêng biệt.

## 9. Đo latency đúng cách

Không chỉ ghi một con số average. Thời gian phản hồi thường có phân phối lệch: đa số request nhanh, một số request rất chậm. Hãy theo dõi histogram và các percentile:

| Chỉ số | Cách đọc |
|---|---|
| p50 | Một nửa request nhanh hơn hoặc bằng giá trị này |
| p90 | 90% request nhanh hơn hoặc bằng giá trị này |
| p95 | 95% request nhanh hơn hoặc bằng giá trị này |
| p99 | 99% request nhanh hơn hoặc bằng giá trị này; nhạy với tail latency |
| max | Giá trị lớn nhất quan sát được; dễ bị ảnh hưởng bởi outlier và kích thước mẫu |

Nếu p50 là 40 ms nhưng p99 là 2 giây, average có thể che mất vấn đề của nhóm request chậm. Với dependency, nên ghi histogram riêng theo operation và trạng thái thành công/thất bại khi cần.

Không cộng p99 của từng dependency để suy ra p99 của request tổng. Percentile của tổng thời gian phụ thuộc vào phân phối và tương quan giữa các nhánh. Dùng distributed trace để thấy một request cụ thể chờ ở đâu và đo histogram tổng ở ranh giới request.

### Đo elapsed time bằng System.nanoTime

Trong Java, dùng `System.nanoTime()` để đo thời gian đã trôi qua. Không dùng `System.currentTimeMillis()` cho duration vì đồng hồ lịch có thể được điều chỉnh:

```java
long started = System.nanoTime();
try {
    callDependency();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    recordDependencyLatency(elapsedNanos);
}
```

Đặt mốc bắt đầu và kết thúc đúng ranh giới cần đo. Nếu muốn đo thời gian chờ connection, bắt đầu trước thao tác lấy connection và kết thúc ngay khi lấy được; nếu muốn đo remote call, bắt đầu sau khi đã có connection và kết thúc khi response hoàn tất.

## 10. Ví dụ metric concurrency và thời gian dependency trong Java

`AtomicInteger` có thể đếm số operation đang in-flight; `LongAdder` phù hợp với counter và tổng thời gian có nhiều thread cập nhật. Đoạn mã sau minh họa cách bọc một lời gọi dependency:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

final class DependencyMetrics {
    private final AtomicInteger inFlight = new AtomicInteger();
    private final LongAdder finished = new LongAdder();
    private final LongAdder succeeded = new LongAdder();
    private final LongAdder failures = new LongAdder();
    private final LongAdder totalLatencyNanos = new LongAdder();

    <T> T measure(Callable<T> operation) throws Exception {
        inFlight.incrementAndGet();
        long started = System.nanoTime();
        try {
            T result = operation.call();
            succeeded.increment();
            return result;
        } catch (Exception e) {
            failures.increment();
            throw e;
        } finally {
            totalLatencyNanos.add(System.nanoTime() - started);
            finished.increment();
            inFlight.decrementAndGet();
        }
    }

    int inFlight() {
        return inFlight.get();
    }

    long finished() {
        return finished.sum();
    }

    long succeeded() {
        return succeeded.sum();
    }

    long failures() {
        return failures.sum();
    }

    double averageLatencyMillis() {
        long count = finished.sum();
        return count == 0 ? 0.0
                : totalLatencyNanos.sum() / 1_000_000.0 / count;
    }
}
```

Đoạn mã này hữu ích để minh họa counter và average latency, nhưng chưa thay thế metrics library trong production:

- `inFlight` là snapshot tức thời, có thể thay đổi ngay sau khi đọc.
- `LongAdder.sum()` trong lúc cập nhật đồng thời không bảo đảm snapshot nguyên tử với mọi update đang diễn ra; phù hợp cho metric tổng hợp chứ không phải đồng bộ nghiệp vụ.
- Average không cho biết p95/p99; cần histogram/timer có bucket hoặc percentile phù hợp.
- Nếu `Error` thoát khỏi `Callable`, `finally` vẫn chạy nhưng counter `failures` ở ví dụ chỉ đếm `Exception`; điều chỉnh phân loại theo chính sách metric của ứng dụng.
- Không gắn nhãn metric bằng request ID, user ID hoặc URL có cardinality không giới hạn. Dùng nhãn có tập giá trị hữu hạn như tên dependency, operation và outcome.

Trong ứng dụng thực tế, có thể dùng Micrometer hoặc OpenTelemetry Metrics/Tracing theo stack quan sát đã chọn. Metrics cho biết xu hướng tổng thể; trace cho biết một request cụ thể đã tiêu tốn thời gian ở span nào.

## 11. Áp dụng với virtual thread trong Java 21

Virtual thread giúp xử lý nhiều tác vụ blocking với chi phí thread thấp hơn platform thread, nhưng không làm giảm thời gian dependency phản hồi và không tăng capacity của database hoặc API bên ngoài.

Ví dụ, 5.000 virtual thread có thể cùng chờ database. Điều đó không có nghĩa database có thể xử lý 5.000 query đồng thời. Nếu connection pool chỉ có 30 connection, các task còn lại có thể chờ pool, giữ request context và tăng latency.

Vì vậy, hãy đo và giới hạn riêng:

- Request in-flight tại ingress/service.
- Số operation đang giữ connection.
- Số operation đang chờ connection pool.
- Số call đồng thời tới từng dependency.
- Số virtual thread đang chờ và thời gian chờ của chúng.

Không dùng số carrier thread làm đại diện cho số request đang chờ. Carrier là platform thread thực thi virtual thread; virtual thread đang park vẫn là một công việc in-flight ở tầng ứng dụng dù không giữ carrier.

Nếu dùng `Executors.newVirtualThreadPerTaskExecutor()`, thêm admission control hoặc semaphore cho dependency có giới hạn. Hãy đặt timeout và deadline để task không chờ vô thời hạn, đồng thời truyền cancellation xuống thao tác I/O khi API hỗ trợ.

## 12. Quy trình tìm điểm nghẽn từ số liệu

Khi latency tăng, kiểm tra theo thứ tự để xác định request bị chậm ở đâu:

1. **Offered/admitted/rejected rate:** traffic có vượt khả năng admission không? Từ chối có tăng không?
2. **Throughput:** tốc độ hoàn tất có tăng theo offered load hay đã plateau?
3. **In-flight và queue depth:** request tích tụ ở ingress, worker queue hay dependency pool?
4. **Queue wait:** thời gian chờ trước khi xử lý có tăng không?
5. **Dependency latency:** dependency nào có p95/p99 tăng? Pool wait và remote call duration phần nào tăng?
6. **Utilization và tài nguyên:** CPU, heap, GC, connection, file descriptor, network và giới hạn dịch vụ ngoài đang ở mức nào?
7. **Retry/timeout:** số attempt có tăng làm arrival rate nội bộ cao hơn request gốc không?
8. **Trace:** chọn một số request chậm để xác nhận span nào chiếm thời gian lớn nhất.

Thay đổi từng giới hạn một và đo lại bằng cùng workload. Tăng queue capacity có thể giảm rejection ngắn hạn nhưng làm queue wait và memory tăng; tăng connection pool có thể tăng throughput nếu database còn capacity, nhưng làm database quá tải nếu không còn.

## 13. Thiết kế load test để xác nhận mô hình

Một quy trình đo hữu ích gồm:

- **Warm-up:** cho JVM và ứng dụng ổn định trước khi lấy số liệu; tránh so sánh một lượt cold start với một lượt đã warm-up.
- **Baseline:** đo ở mức tải thấp để biết latency và resource cost cơ bản.
- **Load steps:** tăng offered arrival rate theo từng mức, giữ mỗi mức đủ lâu để quan sát queue và throughput.
- **Saturation test:** xác định thời điểm throughput không tăng tương ứng, latency tail và rejection tăng mạnh.
- **Burst test:** mô phỏng traffic tăng nhanh trong thời gian ngắn để đánh giá khả năng hấp thụ burst.
- **Soak test:** giữ tải ổn định lâu hơn để tìm queue tăng dần, leak, connection không được trả hoặc memory retention.
- **Recovery test:** giảm tải và quan sát queue drain, latency phục hồi và retry có tiếp tục gây áp lực hay không.

Ghi lại cùng lúc offered rate, admitted rate, throughput, in-flight, queue wait, dependency latency, timeout, rejection, CPU, heap và connection pool. Load generator phải có đủ CPU/network để không làm sai kết quả.

JMH phù hợp để đo microbenchmark cho một đoạn code hoặc thao tác nhỏ trong JVM. Nó không thay thế load test open/closed workload để đo service arrival rate, queueing và dependency latency.

## 14. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng offered RPS thay cho admitted rate trong Little's Law | Ước lượng concurrency sai khi có rejection | Đo arrival rate tại đúng ranh giới xử lý |
| Dùng latency toàn request để tính concurrency của một dependency | Ước lượng quá cao hoặc sai phạm vi | Đo arrival rate và residence time riêng của dependency |
| Chỉ đo average latency | Che khuất tail latency | Theo dõi histogram và p50/p95/p99 |
| Cộng p99 của từng dependency | Không phản ánh đúng percentile tổng | Đo request tổng và dùng trace để phân tích nhánh |
| Tăng queue khi throughput đã bão hòa | Chỉ tăng thời gian chờ và bộ nhớ bị giữ | Giới hạn admission, xử lý bottleneck hoặc giảm tải |
| Chỉ nhìn CPU để kết luận capacity | Bỏ sót pool, network và dependency bottleneck | Theo dõi queue, connection, semaphore và remote latency |
| Retry không giới hạn | Khuếch đại arrival rate lúc dependency đang lỗi | Retry budget, backoff, jitter và deadline |
| Cho rằng virtual thread tự giải quyết quá tải | Nhiều task vẫn giữ memory và chờ tài nguyên hữu hạn | Giới hạn in-flight và từng dependency |
| Dùng closed load test để kết luận capacity theo RPS | Arrival rate tự giảm khi server chậm | Dùng open workload và theo dõi coordinated omission |

## 15. Checklist mô hình hóa arrival rate và dependency wait

- [ ] Định nghĩa rõ ranh giới request và từng dependency operation.
- [ ] Đo offered rate, admitted rate, completed throughput và rejected rate riêng.
- [ ] Dùng Little's Law với arrival rate và thời gian trung bình cùng một ranh giới.
- [ ] Xác nhận hệ thống đủ ổn định trước khi diễn giải concurrency trung bình.
- [ ] Tính arrival rate từng dependency theo số lần gọi trung bình, fan-out và retry.
- [ ] Đo riêng queue wait, connection acquisition wait và remote call duration.
- [ ] Theo dõi in-flight và queue depth cùng p50/p95/p99 latency.
- [ ] Ước lượng pool capacity từ số slot và thời gian giữ slot, rồi xác nhận bằng load test.
- [ ] Dùng open workload nếu cần xác định capacity theo arrival rate độc lập.
- [ ] Giới hạn retry, timeout, request deadline và concurrency tới dependency.
- [ ] Với virtual thread, không nhầm số virtual thread với số carrier hoặc capacity dependency.
- [ ] Thử tải tăng dần, burst, soak và recovery bằng workload có thể lặp lại.

## Tài liệu tham khảo

- [ThreadPoolExecutor — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): pool size, queue và rejection behavior khi tải vượt capacity.
- [Semaphore — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html): giới hạn số operation đồng thời bằng permit.
- [LongAdder — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counter có contention thấp cho thống kê nhiều thread cập nhật.
- [System.nanoTime — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()): đo thời gian trôi qua trong JVM.
- [Virtual Threads — Java SE 21 Guide](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): mô hình virtual thread, scheduler và giới hạn tài nguyên cần quản lý.
- [OpenTelemetry Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/): đo counter, histogram và các tín hiệu tổng hợp.
- [OpenTelemetry Traces](https://opentelemetry.io/docs/concepts/signals/traces/): phân tích thời gian từng span và quan hệ giữa các lời gọi dependency.
- [JMH — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): đo microbenchmark cho đoạn code JVM; không thay thế load test hệ thống.
