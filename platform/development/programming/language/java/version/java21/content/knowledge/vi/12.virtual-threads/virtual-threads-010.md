# Phân biệt concurrency, parallelism, throughput và latency

Khi thiết kế ứng dụng Java 21, đặc biệt là ứng dụng dùng virtual threads, cần phân biệt bốn khái niệm thường bị nhầm lẫn: **concurrency**, **parallelism**, **throughput** và **latency**. Chúng mô tả những khía cạnh khác nhau của hệ thống: cách nhiều công việc tiến triển, số công việc thực sự chạy cùng lúc, tốc độ hoàn thành công việc và thời gian một công việc cần để hoàn tất.

Virtual threads giúp ứng dụng xử lý nhiều tác vụ có thời gian chờ, đặc biệt là I/O blocking, với chi phí quản lý thread thấp hơn. Chúng không tự làm CPU chạy nhanh hơn và không tự tăng số lõi xử lý. Muốn đánh giá lợi ích thực tế, cần đo throughput và latency trong điều kiện tải phù hợp, đồng thời xác định concurrency và parallelism của workload.

## 1. Concurrency là gì?

**Concurrency (đồng thời)** là khả năng tổ chức nhiều công việc sao cho tiến trình của chúng có thể chồng lấp về thời gian. Một công việc có thể chạy một đoạn, tạm dừng để chờ I/O, rồi tiếp tục sau đó; trong thời gian chờ, công việc khác có thể tiến triển.

Concurrency nói về cách hệ thống quản lý nhiều công việc đang diễn ra, không yêu cầu chúng phải thực thi đúng cùng một thời điểm trên nhiều CPU core.

Ví dụ một máy chủ nhận ba yêu cầu:

1. Yêu cầu A đọc dữ liệu từ cơ sở dữ liệu.
2. Yêu cầu B gọi một dịch vụ HTTP bên ngoài.
3. Yêu cầu C xử lý một tác vụ khác.

Trong khi A chờ cơ sở dữ liệu trả lời, B hoặc C có thể được tiếp tục xử lý. Các công việc có thời gian sống chồng lấp, nên hệ thống đang xử lý chúng concurrently.

Concurrency thường được quan sát qua số lượng tác vụ đang tồn tại hoặc đang chờ hoàn tất tại cùng một khoảng thời gian. Trong hệ thống phục vụ request, đại lượng này thường được gọi là *in-flight requests* hoặc số request đang đồng thời được xử lý.

## 2. Parallelism là gì?

**Parallelism (song song)** là việc nhiều công việc thực sự được thực thi cùng một thời điểm, thường trên các CPU core khác nhau.

Nếu máy có nhiều core và runtime có thể lập lịch các tác vụ phù hợp, nhiều đoạn mã có thể chạy đồng thời về mặt vật lý. Với một core đơn, hệ điều hành có thể luân phiên thời gian CPU giữa nhiều thread; điều đó tạo concurrency nhưng không tạo parallel execution thực sự.

Ví dụ:

```text
Concurrency trên một core:
Thời gian  --->
Core 1:    [ A ] [ B ] [ A ] [ C ] [ B ]

Parallelism trên nhiều core:
Thời gian  --->
Core 1:    [       A       ]
Core 2:    [       B       ]
Core 3:    [       C       ]
```

Sơ đồ chỉ minh họa ý tưởng: concurrency cho phép các công việc tiến triển xen kẽ; parallelism có nhiều công việc thực sự chạy cùng thời điểm.

Concurrency và parallelism có liên quan nhưng không đồng nghĩa. Một ứng dụng có thể có hàng nghìn tác vụ concurrent nhưng tại một thời điểm chỉ một số nhỏ tác vụ được CPU thực thi song song, tùy số core và scheduler.

## 3. Throughput là gì?

**Throughput (thông lượng)** là lượng công việc hệ thống hoàn thành trong một đơn vị thời gian. Với ứng dụng web, thường đo bằng số request hoàn tất mỗi giây (requests/second hoặc RPS). Với hệ thống xử lý dữ liệu, có thể đo số bản ghi, message hoặc job hoàn thành mỗi giây.

Ví dụ, nếu một dịch vụ hoàn tất 900 request trong 10 giây thì throughput trung bình trong khoảng đo là:

\[
\text{Throughput} = \frac{900\ \text{requests}}{10\ \text{seconds}} = 90\ \text{requests/second}
\]

Khi đo throughput, cần xác định rõ đang đếm công việc được gửi đến, được tiếp nhận hay thực sự hoàn thành thành công. Với dịch vụ production, nên theo dõi riêng request thành công, request lỗi và request bị timeout; chỉ đếm số request đến có thể làm throughput trông cao dù hệ thống không hoàn thành được công việc.

Throughput là đặc tính của hệ thống trong một mức tải và điều kiện cụ thể, không phải một con số cố định độc lập với workload. Kích thước request, độ trễ database, cache hit rate, giới hạn kết nối, CPU và cấu hình tải đều có thể làm thay đổi kết quả.

## 4. Latency là gì?

**Latency (độ trễ)** là thời gian một công việc hoặc request cần để đi từ mốc bắt đầu đã xác định đến khi có kết quả. Với request/response, latency thường được đo từ lúc request được gửi hoặc được dịch vụ tiếp nhận đến khi response hoàn tất.

Ví dụ, client gửi request lúc 10:00:00.000 và nhận response lúc 10:00:00.180. Latency end-to-end của request đó là 180 ms.

Latency có thể gồm nhiều thành phần:

- Thời gian chờ trong queue trước khi được xử lý.
- Thời gian xử lý CPU.
- Thời gian chờ database, file system hoặc dịch vụ bên ngoài.
- Thời gian truyền dữ liệu qua mạng và tạo response.

Vì vậy, cần nói rõ đang đo latency ở đâu. *Service time* có thể chỉ đo thời gian dịch vụ thực hiện xử lý; *end-to-end latency* bao gồm cả thời gian chờ và truyền tải trên đường đi của request. Hai số đo này không thể thay thế cho nhau.

Latency thấp thường giúp hệ thống phản hồi nhanh hơn. Tuy nhiên, tối ưu latency của một request không nhất thiết làm throughput tăng, và throughput cao không bảo đảm mọi request đều có latency thấp.

## 5. So sánh bốn khái niệm

| Khái niệm | Câu hỏi trả lời | Đơn vị/biểu hiện thường gặp |
|---|---|---|
| Concurrency | Có bao nhiêu công việc đang cùng tồn tại và tiến triển? | Số tác vụ hoặc request in-flight |
| Parallelism | Có bao nhiêu công việc thực sự chạy cùng lúc? | Số luồng thực thi đồng thời trên CPU core |
| Throughput | Hệ thống hoàn thành bao nhiêu công việc trong một khoảng thời gian? | Request/second, jobs/second, records/second |
| Latency | Một công việc mất bao lâu để hoàn tất? | Millisecond, second; thường theo percentile |

Ví dụ một dịch vụ có 500 request đang in-flight, 8 core có thể thực thi CPU song song, hoàn tất 1.000 request mỗi giây và có p95 latency là 120 ms. Bốn con số này mô tả bốn khía cạnh khác nhau; không thể suy ra trực tiếp con số này chỉ từ con số kia nếu chưa biết workload và giới hạn hệ thống.

## 6. Quan hệ giữa concurrency, throughput và latency

Trong một hệ thống ổn định, có thể dùng **Little's Law** để liên hệ số công việc trung bình trong hệ thống, throughput và thời gian trung bình một công việc ở trong hệ thống:

\[
N = \lambda \times W
\]

Trong đó:

- \(N\): số công việc trung bình đang ở trong hệ thống (ví dụ request in-flight).
- \(\lambda\): throughput trung bình, tính bằng công việc hoàn thành trên một đơn vị thời gian.
- \(W\): thời gian trung bình một công việc ở trong hệ thống, tức latency trung bình theo cùng ranh giới đo.

Ví dụ, nếu dịch vụ hoàn tất trung bình 200 request/giây và mỗi request mất trung bình 0,25 giây trong hệ thống thì số request trung bình đang in-flight là:

\[
N = 200 \times 0.25 = 50\ \text{requests}
\]

Kết quả 50 là số trung bình trong điều kiện ổn định, không phải giới hạn concurrency, số thread cần tạo hoặc số request tối đa được phép nhận. Little's Law cũng không nói rằng tăng concurrency tùy ý sẽ làm throughput tăng mãi.

Khi tải tăng, throughput thường tăng theo cho đến khi một tài nguyên trở thành nút thắt. Sau điểm bão hòa, throughput có thể gần như không tăng thêm trong khi queue dài hơn và latency tăng mạnh.

```text
Tải đưa vào tăng
      |
      v
Throughput tăng -------> gần mức bão hòa
                              |
                              +-- thêm tải: throughput ít tăng
                                  nhưng queue và latency tăng
```

Đây là lý do không nên chỉ tối ưu số lượng request đồng thời. Cần biết tài nguyên nào đang giới hạn hệ thống và theo dõi cả tốc độ hoàn thành lẫn thời gian phản hồi.

## 7. Latency trung bình và các percentile

Chỉ xem latency trung bình có thể che khuất những request rất chậm. Một dịch vụ có thể có average latency tốt nhưng một tỷ lệ nhỏ người dùng vẫn phải chờ lâu.

Các percentile thường dùng:

- **p50**: 50% request hoàn tất trong thời gian bằng hoặc thấp hơn giá trị này; thường gọi là median.
- **p95**: 95% request hoàn tất trong thời gian bằng hoặc thấp hơn giá trị này.
- **p99**: 99% request hoàn tất trong thời gian bằng hoặc thấp hơn giá trị này.

Ví dụ:

| Chỉ số | Latency |
|---|---:|
| p50 | 35 ms |
| p95 | 120 ms |
| p99 | 420 ms |

Phần lớn request phản hồi nhanh, nhưng 1% request chậm nhất mất ít nhất khoảng 420 ms theo phân phối đo. Khi đánh giá chất lượng dịch vụ, nên xem p95/p99 cùng average, throughput, error rate và timeout rate.

Percentile phải được tính trên tập mẫu và khoảng thời gian có ý nghĩa. Một lượng request quá nhỏ, một workload không đại diện hoặc trộn các endpoint có đặc tính khác nhau có thể khiến percentile khó diễn giải. Nên phân tách metric theo endpoint hoặc nhóm workload khi cần tìm nguyên nhân.

## 8. Virtual threads ảnh hưởng thế nào đến concurrency và parallelism?

Virtual threads là thread nhẹ do JVM quản lý, được chính thức hỗ trợ từ Java 21. Chúng giúp mô hình lập trình thread-per-task có thể mở rộng đến số lượng lớn tác vụ, đặc biệt khi tác vụ thường chờ I/O.

Ví dụ tạo một virtual thread cho mỗi tác vụ:

```java
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.stream.IntStream;

public class VirtualThreadConcurrencyDemo {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var futures = IntStream.range(0, 100)
                    .mapToObj(id -> executor.submit(() -> {
                        // Mô phỏng một thao tác chờ I/O.
                        Thread.sleep(100);
                        return "Completed task " + id;
                    }))
                    .toList();

            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        }
    }
}
```

Các tác vụ có thể cùng tồn tại dưới dạng virtual threads. Khi một tác vụ thực hiện thao tác blocking được JVM hỗ trợ, virtual thread có thể bị unmount khỏi carrier thread trong lúc chờ, để carrier thực hiện công việc khác. Điều này giúp tăng khả năng xử lý nhiều tác vụ I/O-bound mà không cần tạo một platform thread cho mỗi tác vụ.

`Thread.sleep(100)` trong ví dụ chỉ minh họa thời gian chờ, không phải phép đo hiệu năng hay mô phỏng đầy đủ một lời gọi I/O thực tế. Số tác vụ được chọn để minh họa concurrency, không phải khuyến nghị đặt giới hạn tải production ở con số đó.

Virtual threads **không tự làm tăng parallelism của CPU**. Tại một thời điểm, số tác vụ thực thi CPU song song vẫn bị giới hạn bởi số core khả dụng và scheduler. Nếu mỗi tác vụ chủ yếu thực hiện phép tính CPU-bound, chuyển từ platform thread sang virtual thread thường không làm phép tính hoàn thành nhanh hơn; tạo quá nhiều tác vụ còn có thể làm tăng chi phí lập lịch và tranh chấp tài nguyên.

Vì vậy:

- Với workload I/O-bound có nhiều thời gian chờ, virtual threads có thể hỗ trợ concurrency cao và cải thiện throughput tổng thể nếu thread management trước đó là nút thắt.
- Với workload CPU-bound, cần tập trung vào hiệu quả thuật toán, số core, phân chia công việc và mức parallelism hợp lý.
- Với mọi workload, throughput cuối cùng vẫn phụ thuộc vào database, connection pool, dịch vụ bên ngoài, CPU, mạng và giới hạn tài nguyên khác.

## 9. Nhiều virtual threads không có nghĩa là tài nguyên vô hạn

Virtual threads làm giảm chi phí tạo và chờ thread, nhưng không làm tăng dung lượng của database connection pool, giới hạn API bên ngoài, bộ nhớ hoặc số kết nối mạng mà hệ thống có thể duy trì.

Ví dụ, một dịch vụ có thể tạo nhiều virtual threads để xử lý request, nhưng database chỉ cho phép 40 kết nối đồng thời. Nếu hàng trăm tác vụ cùng cần database, phần còn lại vẫn phải chờ lấy connection. Queue ở connection pool có thể trở thành nguyên nhân làm latency tăng.

Hãy giới hạn tài nguyên khan hiếm tại đúng ranh giới, ví dụ dùng connection pool có kích thước phù hợp hoặc `Semaphore` để giới hạn số lời gọi đồng thời tới một dịch vụ. Không dùng pool platform thread như cách mặc định để quản lý virtual threads; mô hình thông dụng là tạo một virtual thread cho mỗi task và giới hạn riêng tài nguyên thực sự khan hiếm.

Ví dụ giới hạn số thao tác gọi dịch vụ ngoài cùng lúc:

```java
import java.util.concurrent.Semaphore;

class RemoteServiceClient {
    private final Semaphore permits = new Semaphore(30);

    String callRemoteService() throws InterruptedException {
        permits.acquire();
        try {
            return performBlockingRequest();
        } finally {
            permits.release();
        }
    }

    private String performBlockingRequest() {
        // Thực hiện lời gọi I/O blocking tới dịch vụ bên ngoài.
        return "response";
    }
}
```

Semaphore trong ví dụ giới hạn tối đa 30 lời gọi đang giữ permit. Con số 30 chỉ là minh họa; giới hạn thực tế cần dựa trên quota, connection pool, latency và khả năng của dịch vụ đích. Khi bị giới hạn, virtual threads có thể chờ permit mà không cần giữ một platform thread trong suốt thời gian chờ thông thường.

## 10. Đo throughput và latency đúng cách

Để so sánh platform threads và virtual threads, hoặc so sánh hai cách triển khai, hãy đo cùng một workload và cùng điều kiện môi trường.

Một quy trình đo có thể gồm:

1. **Xác định workload:** số request, kích thước dữ liệu, tỷ lệ đọc/ghi, thời gian chờ I/O và tỷ lệ lỗi.
2. **Tạo tải thực tế:** thử nhiều mức concurrency, tăng dần đến khi tìm được điểm bão hòa.
3. **Warm up:** cho JVM và ứng dụng có thời gian khởi động, nạp lớp và tối ưu JIT trước khi lấy số liệu chính.
4. **Đo đủ lâu:** tránh kết luận từ một vài request hoặc một khoảng thời gian quá ngắn.
5. **Thu thập nhiều metric:** throughput thành công, p50/p95/p99 latency, error rate, timeout, CPU, heap, GC, số request in-flight và thời gian chờ ở pool.
6. **Lặp lại:** chạy nhiều lần với cùng cấu hình và so sánh kết quả trong điều kiện tương đương.

Không nên đặt `System.out.println()` trong đường xử lý đang đo vì console I/O có thể làm sai lệch kết quả. `System.nanoTime()` phù hợp để đo khoảng thời gian trong một tiến trình, nhưng một vòng lặp tự viết đơn giản không thay thế được benchmark có kiểm soát. Với microbenchmark CPU, dùng công cụ như JMH; với dịch vụ end-to-end, dùng load test và metrics của hệ thống.

### Cách diễn giải kết quả

| Quan sát | Có thể cho thấy | Cần kiểm tra thêm |
|---|---|---|
| Throughput tăng, p95/p99 ổn định | Hệ thống hoàn thành nhiều việc hơn mà chất lượng phản hồi vẫn giữ được | Error rate, tài nguyên và tính đại diện của tải |
| Throughput gần như không tăng, latency tăng nhanh | Hệ thống có thể đã chạm nút thắt hoặc queue đang tăng | CPU, DB pool, downstream latency, queue depth và timeout |
| CPU cao, throughput không tăng | CPU có thể là nút thắt hoặc công việc đang tranh chấp CPU | Profile CPU, thuật toán, GC và mức parallelism |
| CPU thấp, nhiều request chờ | Có thể đang chờ I/O, connection hoặc giới hạn downstream | Thời gian chờ database/network/pool và số request in-flight |
| Average tốt nhưng p99 cao | Một phần nhỏ request chịu tail latency lớn | Outlier, retry, GC pause, queue và endpoint cụ thể |

Không kết luận virtual threads tốt hơn chỉ vì có thể tạo nhiều thread hơn. Kết luận phải dựa trên throughput, latency, lỗi và mức tiêu thụ tài nguyên dưới cùng điều kiện tải.

## 11. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Concurrency và parallelism là một | Concurrency là nhiều công việc cùng tiến triển; parallelism là thực thi thực sự cùng thời điểm |
| Nhiều thread hơn luôn làm throughput tăng | Tăng concurrency có thể giúp che thời gian chờ, nhưng cũng có thể làm queue và tranh chấp tăng |
| Virtual threads làm CPU có thêm core | Virtual threads không tăng số core và không tự tăng CPU parallelism |
| Throughput cao nghĩa là latency thấp | Hệ thống có thể hoàn thành nhiều request mỗi giây nhưng một số request vẫn phải chờ rất lâu |
| Average latency đại diện cho mọi request | Cần xem percentile như p95/p99 để nhận diện tail latency |
| Tăng số virtual threads giải quyết được giới hạn database | Database pool và quota downstream vẫn là giới hạn riêng cần quản lý |
| `Thread.sleep()` là phép đo I/O | Sleep chỉ mô phỏng chờ; benchmark cần workload và môi trường thực tế |

## 12. Checklist khi thiết kế ứng dụng dùng virtual threads

- Phân loại workload là I/O-bound, CPU-bound hay kết hợp.
- Xác định concurrency cần phục vụ và parallelism CPU thực tế có thể đạt.
- Đo throughput bằng số tác vụ hoàn tất thành công trong một khoảng thời gian rõ ràng.
- Đo end-to-end latency và theo dõi p50, p95, p99 thay vì chỉ xem trung bình.
- Theo dõi số request in-flight, queue, error rate và timeout.
- Kiểm tra các tài nguyên giới hạn như database connection pool, HTTP connection, quota và bộ nhớ.
- Dùng virtual threads để tổ chức nhiều tác vụ blocking phù hợp; không kỳ vọng chúng tăng tốc phép tính CPU-bound.
- Giới hạn tài nguyên khan hiếm tại đúng nơi cần giới hạn thay vì giới hạn số virtual threads một cách tùy tiện.
- So sánh hiệu năng bằng workload, thời gian warm-up và điều kiện môi trường tương đương.

Concurrency, parallelism, throughput và latency là bốn góc nhìn bổ sung cho nhau khi đánh giá ứng dụng. Virtual threads trong Java 21 chủ yếu giúp tổ chức concurrency hiệu quả cho các tác vụ thường chờ I/O; còn throughput và latency vẫn phụ thuộc vào toàn bộ đường xử lý và các tài nguyên phía sau. Đo đúng các chỉ số này sẽ giúp quyết định khi nào virtual threads đem lại lợi ích và đâu là nút thắt thực sự của hệ thống.
