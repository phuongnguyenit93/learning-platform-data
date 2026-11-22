# Ước lượng công suất rồi kiểm chứng bằng phép đo tải

## 1. Mục tiêu: từ dự đoán đến giới hạn đã được đo

Trong ứng dụng Spring Framework dùng `TaskExecutor`, đặc biệt là `ThreadPoolTaskExecutor`, cấu hình số thread và hàng đợi thường bắt đầu bằng một **ước lượng**: hệ thống phải nhận bao nhiêu tác vụ mỗi giây, mỗi tác vụ giữ worker trong bao lâu, và dịch vụ phụ thuộc có thể xử lý bao nhiêu việc song song? Sau đó phải **kiểm chứng bằng tải thực tế** để biết ước lượng ấy có đáp ứng mục tiêu về độ trễ, lỗi và tài nguyên không.

Ví dụ một service nhận yêu cầu tạo báo cáo. Nếu chỉ nhìn CPU hiện tại rồi đặt `maxPoolSize=100`, rất có thể pool thực sự không chạy tới 100 thread vì queue còn rộng, hoặc 100 thread cùng tranh chấp 10 kết nối database. Tăng thread có thể làm backlog, timeout và độ trễ tăng. Cách tiếp cận đúng là đặt giả thuyết định lượng, chọn cấu hình thử nghiệm, đo ở nhiều mức tải và sửa cấu hình theo **điểm nghẽn được quan sát**.

Mạch quyết định:

```text
Nhu cầu (jobs/s) + thời gian mỗi job + SLO
                    |
                    v
          Ước lượng concurrency
                    |
                    v
      Chọn core / max / queue / giới hạn phụ thuộc
                    |
                    v
          Sinh tải có kiểm soát
                    |
                    v
 So offered rate, throughput, latency, queue, lỗi
                    |
                    v
      Điều chỉnh và chạy lại cùng kịch bản
```

**Phạm vi:** bài này tập trung vào công suất xử lý tác vụ trong Spring executor và cách xác thực bằng load test. Công suất của **một instance** khác công suất toàn hệ thống nhiều instance; cả hai phải được phân biệt khi lập kế hoạch.

## 2. Thống nhất đơn vị đo trước khi tính

| Đại lượng | Ký hiệu | Cách hiểu |
| --- | --- | --- |
| Tải được gửi đến (*offered rate*) | `λ_in` | Số task/giây mà phía gọi **cố gắng** gửi |
| Tải được nhận | `λ_accepted` | Số task/giây executor thực sự nhận |
| Tốc độ hoàn tất (*throughput*) | `λ_done` | Số task hoàn tất/giây trong khoảng đo |
| Thời gian xử lý trong worker | `S` (giây) | Từ lúc task **bắt đầu chạy** đến lúc kết thúc; gồm thời gian task chờ I/O trong worker |
| Thời gian chờ queue | `W_q` (giây) | Từ lúc tác vụ được nhận đến khi có worker bắt đầu chạy |
| Thời gian hoàn tất toàn tác vụ | `W` (giây) | Gần bằng `W_q + S`, chưa kể các bước nằm ngoài ranh giới đo |
| Số worker đồng thời | `m` | Số thread tối đa có thể xử lý task tại thời điểm đó |
| Số việc đang chờ | `Q` | Độ dài hàng đợi nội bộ executor |
| Tỷ lệ worker bận | `u` | Xấp xỉ busy workers trung bình / số worker khả dụng |

**Đơn vị phải nhất quán.** Nếu `λ=100 jobs/s`, còn `S=80 ms`, hãy đổi thành `0,080 s` trước khi nhân. Chỉ số trung bình dùng để tính công suất ban đầu; các percentile p95/p99 được dùng để đánh giá độ trễ người dùng và tail latency. Không lấy p95 thay vào định luật Little rồi coi đó là công thức chính xác.

Một điểm rất dễ nhầm: HTTP endpoint có thể trả `202 Accepted` ngay sau khi enqueue task. Khi ấy `http_req_duration` đo **thời gian nhận việc**, không đo **thời gian task hoàn tất**. Để tính công suất xử lý hậu trường, phải đo riêng `submit → start → finish`.

## 3. Ước lượng từ arrival rate và thời gian giữ worker

Ở trạng thái đủ ổn định, nếu trung bình nhận và xử lý `λ` task mỗi giây, mỗi task chiếm một worker trong `S` giây, thì số worker bận trung bình xấp xỉ:

```text
busyWorkers ≈ λ × S
```

Đây là cách áp dụng logic cân bằng luồng công việc (liên quan đến định luật Little), **khi tải không tăng backlog vô hạn** và phép đo cùng một ranh giới. Để chừa khoảng trống cho biến động, có thể đặt tỷ lệ chiếm dụng worker mục tiêu `u_target` (ví dụ 70%) rồi ước lượng:

```text
m_initial = ceil((λ × S) / u_target)
```

Giá trị `u_target` là **giả định thiết kế** để tạo headroom, không phải quy tắc bắt buộc của Java/Spring. Đây cũng **không phải** công thức trực tiếp tính CPU utilization: một worker có thể đang chờ network hoặc database trong phần lớn thời gian.

### Ví dụ tính tay

Giả sử một instance dự kiến nhận 100 tác vụ/giây; đo ban đầu cho thấy mỗi tác vụ giữ worker trung bình 80 ms (`S=0,08 s`). Muốn tỷ lệ worker bận ở tải mục tiêu khoảng 70%:

```text
busyWorkers    = 100 × 0.08 = 8
m_initial      = ceil(8 / 0.70) = 12
idealCeiling   = 12 / 0.08 = 150 tasks/s
```

Diễn giải:

- Ở 100 task/s, trung bình khoảng **8 worker** cùng bận nếu `S` giữ ổn định.
- **12 worker** là một điểm bắt đầu để thử nghiệm, không phải kết luận cần đặt đúng 12 trong production.
- **150 task/s** là trần toán học lý tưởng nếu mỗi worker luôn hoàn thành một task trong 80 ms, không có tranh chấp và không tăng `S` khi đồng thời cao hơn. Công suất được chấp nhận theo SLO thường **thấp hơn** trần này.
- Nếu workload hoàn toàn dùng CPU, 100 task/s × 80 ms CPU mỗi task đòi khoảng 8 CPU-seconds/second trước overhead; không thể lấy 12 threads thay thế cho năng lực CPU. Nếu 80 ms chủ yếu là chờ I/O, số CPU cần có thể thấp hơn nhưng giới hạn kết nối/I/O trở thành vấn đề chính.

### Chương trình Java 17+ tính điểm xuất phát

Lưu nội dung sau thành `CapacityEstimate.java`:

```java
import java.util.Locale;

public final class CapacityEstimate {
    public static void main(String[] args) {
        double arrivalRate = 100.0;       // jobs/second
        double workerSeconds = 0.080;     // seconds/job, không tính queue wait
        double targetWorkerUse = 0.70;    // giả định headroom

        double busyWorkers = arrivalRate * workerSeconds;
        int proposedThreads = (int) Math.ceil(busyWorkers / targetWorkerUse);
        double idealCeiling = proposedThreads / workerSeconds;

        System.out.printf(Locale.ROOT,
                "busy workers = %.1f%n", busyWorkers);
        System.out.println("initial threads = " + proposedThreads);
        System.out.printf(Locale.ROOT,
                "ideal ceiling = %.0f jobs/s%n", idealCeiling);
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac CapacityEstimate.java
java CapacityEstimate
```

Stdout xác định:

```text
busy workers = 8.0
initial threads = 12
ideal ceiling = 150 jobs/s
```

Chương trình **chỉ tính giả thuyết**. Nó không đo queue, tỷ lệ lỗi, dịch vụ ngoài hay độ trễ p95. Những giá trị đó phải thu từ load test.

## 4. Ước lượng queue và thời gian chờ khi xuất hiện burst

Pool hữu hạn có thể chịu một đợt đến nhanh trong thời gian ngắn bằng cách xếp hàng. Với công suất hoàn tất bền vững `μ` (jobs/s) đã được **đo thực tế**, nếu đợt tải đến `λ_peak > μ` và không có điều kiện đặc biệt khác, backlog tăng gần:

```text
backlogAdded ≈ (λ_peak - μ) × durationSeconds
```

Ví dụ **minh họa giả định**: giả sử hệ thống thực sự xử lý được 150 jobs/s không giảm tốc. Một burst 180 jobs/s kéo dài 5 giây có thể tăng backlog thêm khoảng `(180-150)×5 = 150 jobs`. Nếu sau đó tải giảm còn 100 jobs/s và công suất vẫn là 150 jobs/s, backlog có thể giảm với tốc độ ròng khoảng 50 jobs/s, tức cần gần 3 giây để giải phóng 150 jobs. Đây là **mô hình đơn giản**, chưa xét phân bố thời gian xử lý, biến động arrivals, rejection và thay đổi công suất khi quá tải.

Queue có 200 ô **có thể chứa 150 job** trong ví dụ trên, nhưng “chứa được” không đồng nghĩa “đáp ứng SLO”: những job cuối burst phải chờ lâu hơn. Queue quá dài đôi khi giữ tỷ lệ lỗi thấp trong ngắn hạn nhưng lại tạo timeout hoặc kết quả trễ tới mức không còn giá trị.

Từ định luật Little ở trạng thái ổn định:

```text
L_system = λ_done × W
```

`L_system` là số task trung bình trong **toàn phạm vi đo** (đang chờ + đang chạy), còn `W` là thời gian trung bình từ khi vào tới khi ra phạm vi ấy. Ví dụ nếu hệ thống hoàn tất 100 jobs/s và thời gian hoàn tất trung bình là 0,25 s thì trung bình có khoảng 25 task cùng tồn tại trong hệ thống. **Không dùng hệ thức trạng thái ổn định để hợp thức hóa một hàng đợi liên tục tăng trong overload**.

## 5. Áp dụng giả thuyết vào ThreadPoolTaskExecutor

`ThreadPoolTaskExecutor` của Spring bọc `java.util.concurrent.ThreadPoolExecutor`. Ba tham số quyết định việc nhận tải:

- `corePoolSize`: khi số worker dưới ngưỡng core, pool thường tạo thêm worker cho task mới.
- `queueCapacity`: sau khi đạt core, pool thường ưu tiên đặt task vào queue còn chỗ.
- `maxPoolSize`: pool chỉ mở rộng quá core khi **queue không nhận thêm task**. Khi queue cũng đầy và đã đạt max, task có thể bị từ chối.

Vì thế **không thể chọn `maxPoolSize` độc lập với `queueCapacity`**. Giá trị mặc định của class `ThreadPoolTaskExecutor` là core 1, max rất lớn, queue rất lớn; không nên xem đó là cấu hình sản xuất đã được kiểm chứng. Spring Boot có cơ chế tự cấu hình riêng theo điều kiện/phiên bản, nên hãy xem bean **thực sự** được dùng bởi `@Async` hoặc service.

Ví dụ cấu hình đầu tiên cho kịch bản 12 worker cố định, queue giới hạn, dùng trong một Spring application:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class WorkerCapacityConfig {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(12);
        pool.setMaxPoolSize(12);
        pool.setQueueCapacity(200);
        pool.setThreadNamePrefix("report-");
        return pool;
    }
}
```

Đây là **class cấu hình Spring**, cần `spring-context` tương thích và bean được đưa vào ApplicationContext; nó không biên dịch độc lập bằng chỉ JDK. Container quản lý lifecycle của bean. Cấu hình này được gọi là **giả thuyết thử nghiệm**, không phải lời khuyên mọi hệ thống đều dùng 12/12/200.

Chọn core=max giúp phép đo ban đầu dễ diễn giải hơn: pool không có bước “chờ đầy queue mới tăng lên max”. Sau khi có dữ liệu, ta có thể so sánh cấu hình core nhỏ hơn, max lớn hơn và queue nhỏ hơn để cải thiện cách hấp thụ burst. Nhưng lúc đó phải nhớ thứ tự **core → queue → max → rejection**: nếu queue quá rộng, max lớn chưa chắc tạo thêm concurrency.

`TaskExecutor.execute(Runnable)` chỉ giao việc, không tự cam kết task đã hoàn thành. Với tác vụ async cần thống kê thời gian hoàn tất, phải đo **trong worker**, không chỉ lấy thời gian trả về từ `execute`.

## 6. Điểm nghẽn thật không nhất thiết nằm ở số thread

Trước khi tăng pool, hãy hỏi mỗi task đợi tài nguyên nào:

| Loại tải | Thứ có thể giới hạn trước | Hệ quả khi tăng thread |
| --- | --- | --- |
| Tính toán CPU-bound | Số lõi CPU, CPU quota container, GC | Quá nhiều thread gây chuyển ngữ cảnh, tranh chấp và tăng latency |
| Truy vấn database | Kích thước connection pool, lock/query plan, IOPS | Thread tăng nhưng cùng chờ kết nối hoặc lock |
| HTTP gọi dịch vụ ngoài | Connection pool, timeout, quota/rate limit đối tác | Nhiều call đồng thời hơn có thể gây throttling và retry |
| Tác vụ đọc/ghi tệp | Disk throughput, latency, file descriptor | Thêm thread không bù được giới hạn I/O |
| Hệ thống đồng bộ | Lock contention, critical section, shared state | Số worker tăng nhưng throughput gần như đứng yên |

Nếu pool có 40 threads, nhưng database chỉ cấp 10 connections và mỗi task cần một connection suốt thời gian xử lý, tạo thêm threads có thể chỉ làm tăng thời gian chờ connection. Một executor nhận được nhiều task **không tự chứng minh nghiệp vụ đã xử lý được nhiều task hơn**.

Với nhiều instance, cũng phải tính tổng tải lên dependency. Ví dụ 4 pods × 12 threads = tối đa 48 tác vụ đồng thời vào đoạn xử lý; nếu mỗi tác vụ dùng một connection, database pool toàn cụm và giới hạn DB phải đủ đáp ứng. Hệ thống tăng replicas còn có thể làm tổng số kết nối và tốc độ retry tăng.

## 7. Xác định tiêu chí chấp nhận trước khi load test

Một phép đo chỉ có ý nghĩa khi biết thế nào là “đủ”. Ví dụ **mục tiêu giả định** cho endpoint tạo công việc:

- Ở tải **100 yêu cầu nhận việc/giây** trên cấu hình hạ tầng đã xác định, ít nhất 99,9% công việc được nhận hợp lệ và cuối cùng hoàn tất; có kiểm tra mất/nhân đôi công việc theo hợp đồng nghiệp vụ.
- `p95` của **thời gian hoàn tất end-to-end** không vượt **1 giây**, không chỉ thời gian HTTP trả `202`.
- **Không có từ chối task** ở tải mục tiêu; `queueSize` tăng trong burst thì phải giảm về vùng ổn định sau đó.
- CPU, heap, GC, connection pool và quota dịch vụ ngoài còn khoảng dự phòng đã thống nhất.

Các con số này chỉ minh họa **cách phát biểu tiêu chí**, không phải SLO mặc định của Spring. Thay bằng yêu cầu vận hành thật và ghi rõ thời gian duy trì của phép đo. Việc qua SLO ở 100 jobs/s không có nghĩa sẽ qua ở 150 jobs/s.

**Đặc biệt:** hãy tách “yêu cầu được nhận” khỏi “job được xử lý thành công”. Nếu HTTP trả 202 nhưng task bị `TaskRejectedException` rồi thất lạc, đồ thị HTTP có thể trông đẹp trong khi nghiệp vụ sai.

## 8. Lập kế hoạch phép đo tải có thể tái lập

Một kế hoạch load test nên có những pha sau, thực hiện trên môi trường được phép tạo tải:

| Pha | Mục đích | Dấu hiệu cần quan sát |
| --- | --- | --- |
| Warm-up | Làm nóng JVM/JIT, kết nối, cache, thread | Độ trễ bắt đầu ổn định, tránh nhầm chi phí khởi động với steady state |
| Baseline thấp | Đo `S` khi ít tranh chấp | Thời gian worker, throughput, CPU/GC, thời gian DB/API |
| Tăng tải từng mức | Tìm vùng tăng gần tuyến tính | Accepted/done rate, p95/p99, active threads, queue |
| Tải mục tiêu kéo dài | Kiểm chứng SLO bền vững | Backlog không tăng liên tục, ít lỗi, GC/CPU/connection ổn định |
| Burst ngắn | Đánh giá giới hạn queue và khôi phục | Rejection, đỉnh queue, queue-wait, thời gian drain |
| Overload có kiểm soát | Xác định điểm mất SLO và cơ chế bảo vệ | Timeout, `TaskRejectedException`, lỗi downstream, retry amplification |
| Recovery / soak | Xem hệ thống trở lại bình thường và có rò rỉ không | Pool/queue trở lại nền, memory không tăng vô hạn, hoàn tất task tồn |

Để phép so sánh cấu hình công bằng, giữ nguyên loại tác vụ, payload, dữ liệu thử, số instance, CPU/memory quota, connection pool, trạng thái cache và cách đo. Ghi lại cấu hình ở mỗi lượt. Nếu đồng thời thay dữ liệu, network và `maxPoolSize`, sẽ khó xác định nguyên nhân cải thiện hoặc suy giảm.

Nguồn tạo tải cũng có giới hạn; theo dõi CPU/network của load generator và số request thực sự phát được. Dùng payload đại diện: tác vụ “sleep 10ms” không thể thay cho báo cáo thật chứa nhiều truy vấn DB hoặc mã hóa tệp.

## 9. Ví dụ k6: đo tải đến theo jobs/giây

Công cụ như **Grafana k6** hỗ trợ kịch bản `constant-arrival-rate`: bắt đầu iteration theo tốc độ mục tiêu, tương đối độc lập với thời gian response. Điều này hữu ích khi kiểm tra “server có chịu 100 yêu cầu/giây không?”. Mô hình số VU cố định có thể làm tốc độ đến **tự giảm** khi server chậm, che bớt điểm quá tải.

Giả sử ứng dụng thử nghiệm có API **minh họa** `POST /api/jobs` trả `202` sau khi nhận công việc. Tạo tệp `load.js`:

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    jobs: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || '50'),
      timeUnit: '1s',
      duration: '4m',
      preAllocatedVUs: 100,
      maxVUs: 250
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
    dropped_iterations: ['count==0'],
    checks: ['rate>0.99']
  }
};

export default function () {
  const payload = JSON.stringify({
    requestKey: 'perf-' + __VU + '-' + __ITER
  });

  const response = http.post(
    __ENV.BASE_URL + '/api/jobs',
    payload,
    { headers: { 'Content-Type': 'application/json' } }
  );

  check(response, {
    'accepted with 202': (r) => r.status === 202
  });
}
```

Đây là **mẫu k6 chạy độc lập với Java**, nhưng **chỉ chạy đúng khi môi trường thử nghiệm có endpoint `/api/jobs` với hợp đồng 202 và payload như ví dụ**. Nếu API thật khác, điều chỉnh đường dẫn, payload, xác thực và định nghĩa thành công trước khi đo. Không sử dụng trực tiếp để gây tải trên một hệ thống đang phục vụ người dùng nếu chưa có kế hoạch thử tải.

Tại máy có cài k6, có thể thử các mức được kiểm soát riêng:

```bash
k6 run -e BASE_URL=http://localhost:8080 -e RATE=20 load.js
k6 run -e BASE_URL=http://localhost:8080 -e RATE=50 load.js
k6 run -e BASE_URL=http://localhost:8080 -e RATE=100 load.js
k6 run -e BASE_URL=http://localhost:8080 -e RATE=140 load.js
```

Các lệnh minh họa **các lượt chạy riêng**, không phải output có sẵn. Chạy lại mỗi mức sau khi môi trường đã trở về trạng thái nền; không tăng tải một cách mù quáng nếu đã có dấu hiệu không an toàn hoặc đã vượt giới hạn được phép.

Ở đây `rate` nghĩa là **iterations/giây**. Mỗi iteration có đúng một HTTP POST nên xấp xỉ số lần gửi request/giây, miễn là có đủ VU và mạng không giới hạn. `dropped_iterations` tăng có thể là do k6 thiếu VU hoặc server trở nên quá chậm khiến VU không được giải phóng; không được quy ngay nguyên nhân cho executor Spring. Mẫu không thêm `sleep()` cuối iteration vì `constant-arrival-rate` đã điều tiết tốc độ gửi.

Threshold `p(95)<500` trong script chỉ kiểm tra **HTTP admission latency** dưới 500 ms; nó không xác nhận thời gian job chạy xong. Phải có metric nghiệp vụ hoặc phép truy vấn trạng thái job (nếu hợp đồng có hỗ trợ) để kiểm tra end-to-end SLO, tỷ lệ hoàn tất, tính đúng và mất việc.

## 10. Những metric phải quan sát đồng thời

Tại thời điểm chạy test, nên vẽ các chuỗi thời gian theo **cùng timestamp**:

| Nhóm | Metric gợi ý | Câu hỏi được trả lời |
| --- | --- | --- |
| Tải vào | tasks submitted/s, HTTP RPS, offered rate k6 | Gửi bao nhiêu việc tới hệ thống? |
| Tiếp nhận | tasks accepted/s, rejected/s, HTTP 2xx/4xx/5xx | Bao nhiêu việc thực sự vào queue/pool? |
| Xử lý | tasks completed/s, failed/s | Công suất thực sự hoàn tất là bao nhiêu? |
| Executor | active threads, current pool size, queue size/capacity | Pool bận hay hàng đợi đang tích tụ? |
| Thời gian | queue wait, execution time, end-to-end p50/p95/p99 | Người dùng chờ ở giai đoạn nào? |
| JVM | CPU, GC pause, heap, live threads | Runtime có phải điểm nghẽn? |
| Phụ thuộc | DB connections active/pending, query latency, outbound HTTP latency/quota | Task nghẽn ở DB/dịch vụ ngoài hay executor? |
| Client tạo tải | actual iterations/s, dropped iterations, VUs, generator CPU | Load generator có phát đúng tải mục tiêu không? |

Trong `ThreadPoolTaskExecutor`, các API như `getActiveCount()`, `getPoolSize()`, `getQueueSize()` và `getThreadPoolExecutor().getCompletedTaskCount()` cung cấp số đo theo thời điểm (có thể xấp xỉ khi concurrency cao). Micrometer có binder cho các executor được đăng ký thích hợp; **không mặc định mọi bean đều tự xuất đầy đủ metric** trong mọi cấu hình Spring thuần.

Để đo **queue wait** chính xác hơn, có thể bọc task: ghi `submittedAt` trước khi gọi `execute`, ghi `startedAt` trong `Runnable.run()`, ghi `finishedAt` trong `finally`, rồi tính `startedAt - submittedAt` và `finishedAt - startedAt` bằng `System.nanoTime()`. Cần ghi nhận cả nhánh rejected/failed để mẫu đo không thiên về các task thành công. Khi ghi metric, tránh tạo tag có độ biến thiên quá lớn như mỗi `requestId`.

**Nhìn vào xu hướng, không chỉ snapshot.** `queueSize=100` tại một thời điểm có thể là một burst sắp hết; queue 100 rồi 150 rồi 200 trong nhiều phút ở tải không đổi cho thấy backlog có thể không được giải phóng.

## 11. Cách đọc kết quả và quyết định điều chỉnh

Phân tích theo bảng dấu hiệu:

| Triệu chứng dưới tải | Giả thuyết cần kiểm tra | Hành động thử có kiểm soát |
| --- | --- | --- |
| Queue tăng, active threads gần core, chưa tới max | Queue còn rộng nên chưa mở rộng vượt core | Xem lại core và queue; đo lại tail latency |
| Queue đầy, active threads gần max, rejection tăng | Tải vượt công suất thực tế | Giảm offered rate, đặt giới hạn đầu vào, tối ưu task, cân nhắc thêm năng lực thực |
| CPU sát quota, nhiều context switches, throughput không tăng khi thêm threads | CPU-bound/overthreading | Giảm concurrency hoặc tăng CPU; đo CPU time/task |
| CPU thấp nhưng threads bận, DB pool chờ connection | Nghẽn database/connection pool | Tối ưu query, giảm thời gian giữ connection, chỉnh giới hạn phù hợp |
| HTTP trả 202 nhanh nhưng thời gian job hoàn tất tăng | Queue/workers phía sau đang nghẽn | Đo end-to-end latency và backlog, không dùng mỗi HTTP p95 |
| Tăng thread làm p99 xấu hơn, lỗi downstream nhiều | Tăng áp lực lên phụ thuộc hoặc tranh chấp | So sánh cùng tải với cấu hình cũ; hạn chế concurrency |
| Queue giảm sau burst, p95 phục hồi, không mất job | Hấp thụ burst và phục hồi có vẻ tốt | Kiểm chứng lại ở burst dài hơn và tải nền khác |
| k6 dropped iterations tăng | Có thể thiếu VU/generator hoặc server chậm | Kiểm tra giới hạn generator và latency trước khi kết luận capacity |

Phải phân biệt bốn giới hạn:

1. **Admission capacity:** tốc độ hệ thống có thể nhận request/task mà chưa bắt đầu trả lỗi.
2. **Processing capacity:** tốc độ task thực sự hoàn tất đúng.
3. **SLO capacity:** tốc độ cao nhất vẫn đạt yêu cầu latency, error, recovery và tài nguyên.
4. **Burst tolerance:** mức vượt tải trong thời gian ngắn mà queue, deadline và chính sách từ chối vẫn kiểm soát được.

Giới hạn được dùng để hoạch định vận hành thường là **SLO capacity**, thấp hơn các con số “đẩy được task vào queue” hoặc “có thể tạo thêm thread”.

## 12. Khi nào có thể kết luận đã kiểm chứng?

Một cấu hình có thể được chấp nhận tạm thời khi các lượt test đại diện cho tải kỳ vọng cho thấy:

- Có quan sát được **tốc độ gửi, tốc độ nhận và tốc độ hoàn tất**; không lấy HTTP 202 làm bằng chứng task xong.
- Trong pha tải mục tiêu kéo dài, throughput hoàn tất theo kịp offered rate hợp lệ, backlog không tăng không giới hạn, p95/p99 và lỗi đáp ứng SLO đã đặt.
- Giới hạn CPU, heap, GC, DB/API connections, retry, pool size và queue được đánh giá trên đúng loại dữ liệu và số instance dự kiến.
- Khi burst hoặc overload có kiểm soát, hệ thống từ chối/điều tiết theo chính sách rõ ràng và phục hồi; không âm thầm mất hoặc lặp job ngoài hợp đồng.
- Kết quả được chạy lại, lưu kèm phiên bản build, cấu hình executor, kích thước pool phụ thuộc, mức tải, thời gian đo và biểu đồ; thay đổi thông số thì kiểm tra lại.

**Lưu ý:** load test không chứng minh mọi điều kiện tương lai đều an toàn. Các khác biệt về kích thước dữ liệu, cache lạnh, sự cố downstream, GC, mạng và phân phối thời gian xử lý có thể làm công suất thay đổi. Ước lượng + phép đo là một vòng lặp hiệu chỉnh, không phải công thức dùng một lần.

## 13. Sai lầm phổ biến

1. **Lấy số CPU cores nhân một hằng số cố định để đặt thread pool cho mọi workload.** Cần đo thời gian giữ worker, tỷ lệ CPU/I/O wait và giới hạn phụ thuộc.
2. **Dùng p95 thay cho thời gian trung bình trong công thức Little.** Định luật dùng trung bình ở trạng thái ổn định; p95 là ràng buộc độ trễ riêng.
3. **Chỉ tăng `maxPoolSize` nhưng để queue rất rộng.** Pool có thể giữ gần core mãi vì queue chưa đầy.
4. **Chỉ đo HTTP latency cho tác vụ bất đồng bộ.** Phải theo dõi thời gian hoàn tất thật và tỷ lệ job thành công.
5. **Nhầm tốc độ gửi với throughput.** Nếu 200 jobs/s được gửi nhưng 120 jobs/s hoàn tất, backlog/lỗi có thể tích tụ.
6. **Load test chỉ 15 giây rồi kết luận công suất bền vững.** Hệ thống có thể cần thời gian warm-up và đủ lâu để bộc lộ queue growth, GC hoặc dependency saturation.
7. **Dùng số VU cố định mà không đo arrival rate.** Khi server chậm, VU bị giữ lâu có thể làm tốc độ gửi giảm và che quá tải.
8. **Queue cực lớn để tránh rejection.** Backlog lớn gây timeout, memory pressure và công việc hết giá trị trước khi được xử lý.
9. **Tăng threads mà không theo dõi database và API bên ngoài.** Cải thiện ở executor có thể chuyển nghẽn sang dependency.
10. **Không xác định khả năng của load generator.** Iterations bị rơi do công cụ tạo tải không đủ khiến phép đo capacity sai.
11. **So sánh hai cấu hình trên môi trường khác nhau.** Số pod, CPU quota, dữ liệu, cache và network có thể làm kết quả không còn so sánh được.
12. **Chỉ nhìn throughput cao nhất.** Một cấu hình có thể xử lý nhiều hơn trong vài giây nhưng vi phạm p99, tỷ lệ lỗi hoặc không phục hồi.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Có 100 jobs/s, mỗi job chiếm worker trung bình 80 ms, muốn tải worker quanh 70%. Nên bắt đầu thử bao nhiêu worker?  
**Đáp án:** `ceil((100×0,08)/0,70)=12` worker; đó chỉ là giả thuyết ban đầu.

**Câu 2.** Đặt `core=4`, `max=32`, queue rất lớn. Khi 4 worker bận, pool có tự tăng ngay lên 32 không?  
**Đáp án:** Thường không. Nó ưu tiên xếp hàng nếu queue còn nhận task.

**Câu 3.** Tại mức tải 120 jobs/s, ứng dụng trả HTTP 202 đúng 120 lần/s nhưng chỉ hoàn tất 70 jobs/s. Có thể nói đủ công suất 120 jobs/s không?  
**Đáp án:** Không. Admission rate và processing rate khác nhau; backlog có thể tăng hoặc task lỗi/mất.

**Câu 4.** Vì sao tăng từ 12 lên 40 workers có thể làm p99 tệ hơn dù CPU còn thấp?  
**Đáp án:** Task có thể tranh chấp DB connection, lock, quota API hoặc gây timeout/retry nhiều hơn.

**Câu 5.** Lúc thử tải, queue tăng một phút rồi giảm và về nền; lúc khác queue tăng mãi ở cùng offered rate. Hai tình huống có giống nhau không?  
**Đáp án:** Không. Một tình huống có thể là burst được hấp thụ, tình huống kia gợi ý công suất hoàn tất không theo kịp tải đến.

**Câu 6.** Dựa vào metric nào để phân biệt công suất thực với khả năng tạo tải?  
**Đáp án:** So sánh offered iterations/s, dropped iterations, accepted/s, completed/s và error/latency ở cả load generator lẫn server.

### Tài liệu đối chiếu

- [Spring Framework — ThreadPoolTaskExecutor JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Java SE 17 — ThreadPoolExecutor: core/max, queue, rejection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Micrometer — JVM and Executor metrics](https://docs.micrometer.io/micrometer/reference/1.12/reference/jvm.html)
- [Grafana k6 — Constant arrival rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/)
- [Grafana k6 — Open and closed load models](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/)
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/)
