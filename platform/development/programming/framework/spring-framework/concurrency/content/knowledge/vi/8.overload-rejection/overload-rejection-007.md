# Chọn trả lỗi, hạn chế nhận thêm hoặc lưu công việc bền vững

**Module:** Spring Framework - concurrency  
**Nhóm:** Quá tải và từ chối  
**Mục tiêu:** Khi hệ thống không thể xử lý ngay tất cả yêu cầu, biết lựa chọn và kết hợp ba chiến lược: **trả lỗi sớm**, **kiểm soát tốc độ/số việc được nhận**, hoặc **ghi nhận công việc bền vững để xử lý sau**. Hiểu chính xác hợp đồng HTTP, ranh giới bảo đảm, giới hạn executor của Spring, phục hồi sau lỗi và cách đo quá tải.

## 1. Bài toán: nhiều yêu cầu đến hơn năng lực xử lý

Giả sử API tạo báo cáo được gọi **100 lần/giây**, nhưng dịch vụ chỉ có thể hoàn tất **40 báo cáo/giây** trong một khoảng thời gian dài. Nếu mỗi lời gọi được xếp vào hàng chờ vô hạn, backlog tăng khoảng 60 việc mỗi giây. Sau 10 phút, riêng lượng việc tồn đọng lý thuyết là khoảng 36.000, chưa kể tác vụ thất bại và retry.

Tăng `queueCapacity` hoặc `maxPoolSize` không tự tạo thêm CPU, kết nối DB hay công suất xử lý của dịch vụ bên ngoài. Khi tốc độ đến vượt tốc độ hoàn tất đủ lâu, **bất kỳ hàng đợi hữu hạn nào cũng sẽ đầy**; hàng đợi vô hạn chỉ chuyển lỗi thành trễ lớn và nguy cơ hết bộ nhớ.

Phân biệt ba khái niệm:

- **Nhận yêu cầu HTTP (received):** server đã thấy request trên kết nối mạng. Chưa đồng nghĩa đã nhận trách nhiệm xử lý nghiệp vụ.
- **Chấp nhận công việc (accepted):** server đã nhận công việc theo hợp đồng cụ thể: có thể chỉ giao vào bộ nhớ, hoặc đã ghi vào kho bền vững.
- **Hoàn thành (completed):** nghiệp vụ tạo ra kết quả cuối cùng, thành công hoặc thất bại.

Vì thế, khi backend bận, phản hồi nào đúng phụ thuộc vào **mức cam kết**:

```text
Client gửi yêu cầu
        |
        v
Xác thực + xác minh payload + quyền + quota
        |
        v
Có thể phục vụ ngay / trong deadline?
        |
       Có ----------------------> Xử lý đồng bộ -> 2xx/4xx/5xx theo kết quả
        |
       Không
        |
        +-- Không thể/không nên nhận --> 429 hoặc 503 có chủ đích
        |
        +-- Chỉ cho phép N việc đồng thời -> admission control/bulkhead
        |                                  |
        |                                  +-- Còn chỗ -> nhận/xử lý
        |                                  +-- Hết chỗ -> từ chối sớm
        |
        +-- Có yêu cầu xử lý sau và đủ khả năng lưu bền vững?
                                           |
                                           +-- Ghi nhận thành công -> 202 + jobId
                                           +-- Không ghi được -> trả lỗi, không hứa đã nhận
```

Ba chiến lược **có thể phối hợp**. Chẳng hạn, API giới hạn mỗi khách hàng 20 job/phút, ghi job vào DB khi còn quota và trả `202`; khi hàng chờ đạt mức an toàn thì trả `503`, dù DB còn dung lượng. Không phải cứ có queue là phải nhận mọi request.

## 2. Bảng quyết định: từ chối, hạn chế nhận, hay lưu bền vững?

| Câu hỏi/điều kiện | Trả lỗi sớm | Hạn chế nhận thêm | Lưu việc bền vững |
| --- | --- | --- | --- |
| Client có thể thử lại mà không gây side effect lặp? | Hợp lý nếu có thông tin retry | Hợp lý để kiểm soát burst | Vẫn cần idempotency khi retry |
| Công việc rất ngắn, cần kết quả trong cùng HTTP response? | Từ chối khi quá tải | **Ưu tiên** giới hạn concurrency, hàng chờ rất nhỏ | Thường không đáng chi phí chuyển sang job |
| Công việc dài, có thể chạy sau và client không cần kết quả tức thì? | Nếu chưa có năng lực nhận việc | Dùng để bảo vệ tốc độ đưa vào queue | **Phù hợp** với job + trạng thái |
| Không được mất yêu cầu sau restart? | Client giữ trách nhiệm retry | Chỉ đủ nếu có cơ chế nhận bền vững | **Cần** DB/queue bền vững + recovery |
| Dịch vụ phụ thuộc DB/API bên ngoài đang nghẽn? | Trả lỗi sớm để ngắt dây chuyền | Bulkhead/rate limit theo downstream | Chỉ queue khi deadline, retry và backlog có kiểm soát |
| Hạn mức khác nhau theo người dùng/tenant? | `429` theo quota | Token bucket + quota per tenant | Kết hợp quota và số job đang chờ per tenant |
| Hệ thống đang tự quá tải hoặc tạm bảo trì? | Thường `503` | Giảm admission, load shedding | Có thể tiếp tục ghi nếu kho job và quota còn khỏe |

**Thứ tự suy nghĩ thực tế:**

1. Xác định **SLO/deadline** của client: cần kết quả trước thời điểm nào?
2. Xác định **bất biến nghiệp vụ**: được phép xử lý trùng không, mất việc có chấp nhận không?
3. Xác định **nguồn nghẽn**: CPU, thread, queue, DB connections, remote quota, RAM, disk hay broker.
4. Xác định **khả năng nhận việc an toàn**: bao nhiêu đang chạy, bao nhiêu được chờ, backlog tối đa và thời hạn sống?
5. Chọn phản hồi và bảo đảm đúng với thực tế; sau đó đặt giới hạn, metrics và kiểm thử lỗi.

## 3. Trả lỗi sớm: giữ server và downstream còn phục vụ được

Khi không có cách hoàn thành trong deadline và không thể nhận job an toàn, **từ chối rõ ràng** tốt hơn treo request rồi timeout. Hai HTTP status hay dùng:

### `429 Too Many Requests`: client/tenant chạm quota hoặc rate limit

Theo RFC 6585, `429` diễn tả **quá nhiều yêu cầu theo một giới hạn tốc độ**. Ví dụ một khách hàng dùng hết 60 lượt xuất báo cáo/phút:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 30

{
  "type": "https://example.invalid/problems/rate-limit",
  "title": "Rate limit exceeded",
  "status": 429,
  "detail": "Quota for this client is exhausted."
}
```

Đây là **ví dụ hợp đồng HTTP**, không phải response thật của một máy chủ đang chạy. `Retry-After` có thể là số giây hoặc ngày giờ HTTP; chỉ đưa giá trị khi service có căn cứ ước lượng. Không tự trả cùng một số giây cố định cho mọi tình huống nếu không có logic reset quota.

### `503 Service Unavailable`: service tạm không đủ năng lực nhận thêm

Theo RFC 9110, `503` phù hợp với overload tạm thời hoặc bảo trì:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Retry-After: 5

{
  "type": "https://example.invalid/problems/overloaded",
  "title": "Service temporarily overloaded",
  "status": 503,
  "detail": "No execution capacity is available."
}
```

Một executor đầy, DB không còn connection hoặc broker không nhận message có thể dẫn tới `503` tùy hợp đồng. Không phải mọi lỗi DB đều là quá tải: lỗi dữ liệu, lỗi cấu hình hay lỗi lập trình cần được phân loại riêng.

**`429` hay `503`?** Một giới hạn áp lên **lượng yêu cầu của caller** thường diễn đạt bằng `429`; **năng lực chung của server** tạm không đáp ứng thường là `503`. Trên thực tế có trường hợp hai nguyên nhân cùng xảy ra; thiết kế mã lỗi nghiệp vụ ổn định để client biết lý do và cách retry. Không mặc định rằng việc đầy thread pool luôn là lỗi của client.

### Chính sách retry ở client

- Chỉ retry thao tác khi **idempotent** hoặc có `Idempotency-Key`/deduplication bảo vệ.
- Dùng exponential backoff + jitter; tôn trọng `Retry-After` khi có. Không cho hàng nghìn client retry lại cùng thời điểm.
- Có **retry budget**, deadline tổng và circuit breaker/bulkhead nếu downstream liên tục lỗi.
- Giới hạn retry tại tất cả các tầng: API gateway, SDK, service nội bộ và worker; nhiều tầng retry tự phát có thể nhân request theo cấp số nhân.
- Trả thông tin có ích: mã lỗi, status, correlation ID, gợi ý thử lại; không lộ exception nội bộ, SQL hoặc token nhạy cảm.

Một request bị từ chối **trước khi thực thi** khác request đã thực hiện một phần rồi bị timeout. Với trường hợp thứ hai, client có thể không biết side effect đã xảy ra. Khi đó idempotency và API tra cứu trạng thái càng quan trọng.

## 4. Hạn chế nhận thêm: kiểm soát *rate*, *concurrency* và *backlog*

**Admission control** quyết định *có nhận một công việc mới vào hệ thống hay không* dựa trên ngân sách thực tế. Đây là lớp phòng vệ ở trước hoặc ngay sát executor/downstream, không chỉ xử lý exception sau khi quá tải.

Ba loại giới hạn khác nhau:

| Giới hạn | Điều gì được hạn chế? | Ví dụ | Không bảo đảm điều gì? |
| --- | --- | --- | --- |
| **Rate limit** (token bucket, sliding window) | Số lời gọi trong một khoảng thời gian | Tối đa 100 POST/phút/tenant | Không giới hạn in-flight nếu task chạy rất lâu |
| **Concurrency limit** (semaphore/bulkhead) | Số thao tác đang hoạt động cùng lúc | Tối đa 8 query tới database | Không giới hạn tổng số request/phút khi mỗi thao tác nhanh |
| **Queue/backlog limit** | Số job chờ thực thi, cùng tuổi tối đa | Tối đa 200 job đang `QUEUED` | Không bảo đảm throughput nếu worker quá chậm |

Có thể cần cả ba: rate limit ngăn một tenant gửi ồ ạt; semaphore giới hạn DB calls; hàng chờ hữu hạn giới hạn độ trễ và RAM.

### Semaphore / bulkhead

`Semaphore` là cách đơn giản giới hạn số việc **đồng thời** trong một JVM:

```java
private final java.util.concurrent.Semaphore dbSlots =
        new java.util.concurrent.Semaphore(8);

public Result queryWithLimit(Request request) {
    if (!dbSlots.tryAcquire()) {
        throw new BackendBusyException();
    }
    try {
        return queryDatabase(request);
    } finally {
        dbSlots.release();
    }
}
```

Đây là **đoạn thành viên minh họa**, cần định nghĩa `Result`, `Request`, `BackendBusyException`, `queryDatabase` trong ứng dụng. Lấy permit trước khi dùng downstream, và **luôn** release trong `finally`. `tryAcquire()` không chờ, giúp fail fast; `tryAcquire(timeout, unit)` chỉ phù hợp nếu ngân sách chờ của request còn đủ.

Lưu ý:

- Nếu service có 5 replica, mỗi replica có semaphore 8 permit thì giới hạn lý thuyết **toàn cụm có thể lên tới 40**, không phải 8. Muốn quota toàn cụm, cần cơ chế điều phối chung hoặc phân bổ ngân sách per replica.
- Nếu đã dùng connection pool có tối đa 8 kết nối, semaphore thêm có thể vẫn hữu ích để từ chối sớm thay vì để hàng chục worker chờ lấy connection, nhưng phải đặt số hợp lý so với connection thực và workload khác.
- Đừng giữ permit qua một thao tác không cần thiết như chờ client download, sleep kéo dài hoặc gửi job đã chuyển sang queue riêng; permit phải bảo vệ đúng tài nguyên đang bị giới hạn.

### Vì sao không chỉ tăng hàng chờ?

Giả sử executor hoàn tất 25 job/giây, bạn cho queue 1.000 job. Một job ở cuối queue có thể chờ cỡ **40 giây** nếu pool chạy đều và không có ưu tiên. Nếu deadline client là 2 giây, hàng chờ đó tạo ra kết quả đến quá muộn. Sizing queue cần dựa trên **thời gian chờ chấp nhận được**, lượng burst và throughput thực, không chỉ số chỗ trống trong RAM.

Little's Law, khi hệ thống tương đối ổn định:

\[
L = \lambda \times T
\]

`L` là số công việc trong hệ thống, `λ` là throughput, `T` là thời gian trung bình lưu lại (bao gồm queue nếu đo toàn hệ thống). Công thức không làm overload biến mất; nó nhắc rằng backlog và latency có quan hệ trực tiếp.

### Công bằng và tách nguồn tải

Một tenant gửi rất nhiều job có thể chiếm queue của mọi tenant khác. Cân nhắc quota theo tenant, weighted fair queue hoặc phân pool/hàng đợi theo loại tác vụ. Job khẩn cấp và batch dài ngày thường không nên dùng chung một queue không ưu tiên. Tách tài nguyên phải dựa trên SLO và dự báo tải; nhiều pool nhỏ tạo thêm chi phí thread và giám sát.

## 5. Spring `ThreadPoolTaskExecutor` từ chối lúc nào?

`ThreadPoolTaskExecutor` dùng `ThreadPoolExecutor` JDK ở dưới và đưa ra hợp đồng `TaskExecutor` của Spring. Tham số trọng tâm:

```java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(16);
executor.setRejectedExecutionHandler(
        new java.util.concurrent.ThreadPoolExecutor.AbortPolicy());
```

Đây chỉ là đoạn cấu hình minh họa. Trình tự nhận việc thông thường của `ThreadPoolExecutor`:

1. Khi số worker đang có chưa đạt `corePoolSize`, tạo worker cho task mới.
2. Khi đã đạt core, **đưa task vào queue nếu còn chỗ**.
3. Khi queue không nhận thêm, tạo worker vượt core đến `maxPoolSize`.
4. Khi không thể tạo worker và queue đầy, áp dụng `RejectedExecutionHandler`.

Vì vậy `maxPoolSize=8` **không có nghĩa** executor dùng ngay 8 thread trong khi queue còn rộng. Với queue không giới hạn, pool có thể gần như chỉ chạy bằng core workers, còn backlog tiếp tục phình ra. Một giới hạn **queue hữu hạn** là phần thiết yếu của thiết kế overload.

### Chính sách từ chối

- **`AbortPolicy`** (JDK): ném `RejectedExecutionException`; `ThreadPoolTaskExecutor` trình bày rejection theo hợp đồng Spring `TaskRejectedException`.
- **`CallerRunsPolicy`**: nếu executor chưa shutdown và không nhận task, luồng gửi có thể **tự chạy** task. Với Servlet request thread, đây có thể là block rất lâu; không phù hợp nếu cần trả lỗi nhanh và chắc chắn.
- **`DiscardPolicy`/`DiscardOldestPolicy`**: nguy hiểm cho nghiệp vụ vì task có thể bị bỏ mà caller không biết kết quả; nhất là nếu đã hứa nhận việc.
- Có thể viết policy riêng, nhưng phải định nghĩa rõ khi nào chấp nhận, khi nào báo lỗi và ai chịu trách nhiệm retry.

`ThreadPoolTaskExecutor` mặc định không phải durable queue. Một tác vụ đã vào queue trong JVM có thể **mất khi tiến trình chết**. Khả năng tự từ chối khi đầy là một tầng phòng vệ, không phải bảo đảm xử lý cuối cùng.

### Ví dụ bean Spring có giới hạn rõ

Đây là file cấu hình dùng trong ứng dụng Spring Boot 3.x/Java 17+ có `spring-boot-starter-web` (hoặc Spring Context tương ứng).

**`src/main/java/com/example/overload/ExecutorConfig.java`**:

```java
package com.example.overload;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ExecutorConfig {

    @Bean("shortTaskExecutor")
    public ThreadPoolTaskExecutor shortTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("short-task-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

**`src/main/java/com/example/overload/AdmissionService.java`**:

```java
package com.example.overload;

import java.util.concurrent.Semaphore;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class AdmissionService {
    // Giới hạn tổng số việc đã nhận và chưa xong tại instance này.
    private final Semaphore capacity = new Semaphore(24);
    private final ThreadPoolTaskExecutor executor;

    public AdmissionService(
            @Qualifier("shortTaskExecutor") ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    public boolean trySubmit(Runnable action) {
        if (!capacity.tryAcquire()) {
            return false;
        }
        try {
            executor.execute(() -> {
                try {
                    action.run();
                } finally {
                    capacity.release();
                }
            });
            return true;
        } catch (TaskRejectedException rejected) {
            capacity.release();
            return false;
        }
    }
}
```

Trong ví dụ, concurrency admission thực chất giới hạn **tổng việc đã nhận (đang chạy + đang chờ)** tối đa 24 per instance, tương ứng với trần 8 worker và 16 queue ở trường hợp đầy tải. Đây là **lớp bảo vệ trong RAM**, không phải kho job.

- Controller có thể gọi `trySubmit` và trả `503` khi nhận `false` nếu overload chung; `429` nếu bị từ chối vì hạn mức riêng của caller. Cần một hợp đồng thành công hợp lệ với loại việc và cách theo dõi của ứng dụng.
- **Không** báo `202` với cam kết durable chỉ vì `trySubmit()` trả `true`: task nằm trong JVM, có thể biến mất sau crash.
- Nếu `action.run()` lỗi, permit vẫn được trả về nhưng lỗi nghiệp vụ phải được log/ghi trạng thái theo cơ chế riêng. Không có job-status store trong ví dụ tối giản này.
- `Semaphore` có phạm vi một bean instance. Nhiều replica cần phối hợp với giới hạn tài nguyên thực hoặc giới hạn toàn cụm.
- Đừng bao một tác vụ ở `@Async` bằng một semaphore rồi giữ permit trên **request thread** qua vòng đời không xác định. Hãy chọn rõ thời điểm acquire/release, tránh leak permit khi reject/hủy/timeout.

### Spring exception → HTTP có chủ đích

Nếu giao việc bị từ chối, controller hoặc `@RestControllerAdvice` có thể ánh xạ `TaskRejectedException` sang `503` cho overload chung; nhưng **không** tự map mọi `IllegalStateException` hay `Exception` thành `503`. Kỹ thuật này nên đi kèm `Retry-After` có căn cứ, log/metric và mã lỗi ổn định. Những task đã nhận rồi nhưng thất bại về sau **không thể** sửa lại HTTP response đã trả.

## 6. Khi nào phải lưu công việc bền vững?

Chọn durable job khi **công việc có giá trị và phải tồn tại sau vòng đời request/JVM**, ví dụ xuất báo cáo dài, đối soát, gửi tài liệu theo yêu cầu, xử lý batch, tạo hợp đồng hoặc workflow nhiều bước. Khi client có thể tra cứu kết quả sau, API có thể trả `202 Accepted` kèm mã job.

Mẫu hợp đồng:

```http
POST /reports
Idempotency-Key: request-2026-0001
Content-Type: application/json

{"period":"2026-09"}
```

```http
HTTP/1.1 202 Accepted
Location: /jobs/8b4f
Content-Type: application/json

{
  "jobId": "8b4f",
  "status": "QUEUED",
  "statusUrl": "/jobs/8b4f"
}
```

```http
GET /jobs/8b4f

HTTP/1.1 200 OK
Content-Type: application/json

{
  "jobId": "8b4f",
  "status": "RUNNING",
  "attempts": 1
}
```

Các giá trị ID và payload ở trên là **minh họa**, không phải phản hồi của chương trình demo. `202 Accepted` theo RFC 9110 diễn tả đã nhận để xử lý nhưng **chưa hoàn thành**, và kết quả sau cùng có thể thành công hoặc không. Nên có resource trạng thái để client tra cứu; `200` của `GET` chỉ chứng minh việc **đọc trạng thái** thành công, không chứng minh job `SUCCEEDED`.

### “Đã nhận” là ranh giới nào?

Bốn tình huống phải tách bạch:

1. **Đã đặt vào `ThreadPoolTaskExecutor` trong RAM:** chỉ bảo đảm delegate tạm nhận tại thời điểm gọi; không an toàn sau crash.
2. **Đã ghi record job trong DB và commit:** job được lưu bền vững theo mức cam kết của database và có thể khôi phục/claim sau restart.
3. **Broker đã xác nhận message được lưu theo cấu hình durable thực tế:** có thể được tiêu thụ sau; phải phân biệt publish thành công với chỉ gọi hàm send. Độ bền phụ thuộc broker/quorum/replication/ack policy.
4. **Đã xử lý side effect xong:** mới là hoàn thành nghiệp vụ; có thể xảy ra nhiều lần thử và xử lý trùng nếu thiết kế không idempotent.

Nếu hợp đồng yêu cầu không mất việc, **chỉ trả `202` sau khi ghi nhận bền vững thành công**. Nếu DB commit thất bại hoặc message chưa được broker xác nhận theo bảo đảm cần thiết, phải báo thất bại/tình trạng không xác định phù hợp; không tạo `jobId` trên RAM rồi hứa chắc chắn xử lý.

### Mô hình lưu job đơn giản

```text
Client -> API (auth/validate/quota)
              |
              | BEGIN TRANSACTION
              v
       jobs(status=QUEUED) ----+----> outbox(event=PROCESS_JOB)
              |               |
              +--- COMMIT -----+
                       |
                       +----> HTTP 202 + jobId
                       |
               Outbox publisher
                       |
                       v
                  Message broker
                       |
                       v
              Worker (claim/dedupe)
                       |
                       v
            jobs: RUNNING -> SUCCEEDED/FAILED
                       |
                       v
                GET /jobs/{jobId}
```

Một worker có thể dùng DB trực tiếp làm queue nếu quy mô thích hợp, với cơ chế **claim/lease** và phục hồi job mồ côi. Broker giúp tách producer/consumer và điều tiết phân phối, nhưng không xóa nhu cầu kiểm soát backlog, idempotency và ghi trạng thái.

## 7. Transactional outbox để không mất công việc giữa DB và broker

Một lỗi thường gặp:

```text
1. INSERT job vào DB và COMMIT.
2. Publish message sang broker.
3. Trả HTTP 202.
```

Nếu tiến trình chết giữa bước 1 và 2, DB có job `QUEUED` nhưng broker không biết để chạy. Đảo thứ tự publish trước commit cũng nguy hiểm: worker có thể chạy cho một transaction sau đó rollback.

**Transactional outbox** ghi job và sự kiện cần phát **trong cùng DB transaction**:

```sql
-- PostgreSQL: cấu trúc minh họa, lược giản để tập trung vào bất biến.
CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_job_idem UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE job_outbox (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(id),
    event_type VARCHAR(40) NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Trong một transaction, khi nhận yêu cầu mới:

```sql
BEGIN;

WITH inserted AS (
    INSERT INTO jobs (
        id, tenant_id, idempotency_key, request_hash, status
    )
    VALUES (
        :job_id, :tenant_id, :idempotency_key, :request_hash, 'QUEUED'
    )
    ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
    RETURNING id
)
INSERT INTO job_outbox (job_id, event_type, payload)
SELECT id, 'PROCESS_JOB', jsonb_build_object('jobId', id)
FROM inserted;

COMMIT;
```

Đây là **SQL mẫu PostgreSQL dùng named parameters** (`:job_id`, ...) do framework/JDBC client bind; không chạy nguyên văn trong `psql` nếu chưa thay/bind tham số. Logic nhận yêu cầu phải phân biệt **insert mới** với **duplicate idempotency key**:

- Nếu insert mới, outbox được ghi cùng giao dịch; chỉ sau `COMMIT` mới trả `202` + job ID.
- Nếu conflict trên `(tenant_id, idempotency_key)`, tìm job cũ **cùng tenant**, so sánh request hash. Nếu payload giống, trả cùng job ID; nếu khác, trả `409 Conflict` hoặc mã lỗi hợp đồng vì reuse key cho nội dung khác.
- Cần bảo đảm kiểm tra lại sau transaction race, giữ phân quyền và scope tenant; không chỉ nhìn `affectedRows=0` rồi tạo job khác.
- Worker/publisher phải hỗ trợ event trùng do retry/crash. Outbox giúp tránh **mất thông điệp do khoảng trống DB-then-publish**, nhưng không mang lại exactly-once side effect.

Một publisher thường: đọc các outbox record chưa phát, claim bằng lock/lease, publish với broker confirmation, đánh dấu `published_at` sau khi xác nhận. Nếu publish thành công nhưng publisher chết trước khi ghi `published_at`, event có thể **được phát lại**. Đó là lý do consumer bắt buộc idempotent.

**Không đồng nhất “có DB row” với “job sẽ chắc chắn chạy xong”**. DB vẫn có thể hỏng hoặc đầy; worker có thể xử lý lỗi vĩnh viễn; payload có thể không còn hợp lệ. “Bền vững” nói về khả năng lưu/khôi phục trách nhiệm nhận việc, không phải bảo đảm nghiệp vụ luôn thành công.

## 8. Worker, retry, idempotency và khôi phục sau crash

Một job thường đi qua các trạng thái:

```text
QUEUED -> RUNNING -> SUCCEEDED
              |
              +-> RETRY_WAIT -> QUEUED
              |
              +-> FAILED
              |
              +-> CANCELLED (nếu nghiệp vụ hỗ trợ hủy)
```

Khi cần xử lý chắc chắn:

- **Claim một lần tại một thời điểm:** một worker atomically chuyển job đủ điều kiện từ `QUEUED` sang `RUNNING` (hoặc dùng queue consumer ack contract). DB có thể dùng row locking/lease; tránh hai worker cùng claim một job trong thời điểm bình thường.
- **Lease/heartbeat:** nếu worker chết khi job `RUNNING`, job có thể được tái giao sau khi lease hết hạn; worker cũ sống lại cần fencing/điều kiện version nếu có khả năng ghi muộn.
- **Ack đúng thời điểm:** không ack một broker message trước khi nghiệp vụ và trạng thái đã được ghi theo hợp đồng cần thiết, vì crash giữa hai bước có thể mất trách nhiệm xử lý. Nếu ack sau commit, message có thể được giao lặp và consumer phải chịu được.
- **Retry có phân loại:** lỗi tạm thời (network timeout, quá tải downstream) có thể retry với exponential backoff + jitter; lỗi vĩnh viễn (payload sai, không đủ quyền, dữ liệu không tồn tại) cần `FAILED` có giải thích.
- **Hạn mức retry:** `maxAttempts`, retry deadline, dead-letter queue hoặc trạng thái `FAILED`; job không được lặp vô hạn làm nghẽn queue.
- **Idempotent side effect:** chuyển trạng thái bằng điều kiện version; dùng khóa nghiệp vụ duy nhất, bảng dedupe, hoặc request ID được downstream hỗ trợ. Gửi email/thu tiền/gọi webhook có thể lặp nếu sự cố xảy ra ngay sau side effect nhưng trước ack.
- **Out-of-order & cancellation:** nếu có update trạng thái muộn, dùng điều kiện transition hợp lệ và version. `CANCELLED` không được phép bị worker cũ vô tình ghi thành `SUCCEEDED`.
- **Result retention:** quy định bao lâu được `GET /jobs/{id}`, lưu tệp kết quả ở đâu, bảo vệ tenant data, thời hạn tải và dọn rác có kiểm soát.

### Không có “exactly once” miễn phí

Giả sử worker gọi đối tác để thu tiền; đối tác đã thu tiền thành công, nhưng response mất vì network timeout. Worker không biết giao dịch đã thành công nên retry có thể thu lần hai. Cách khắc phục là dùng **idempotency key tại ranh giới side effect**, hoặc cơ chế reconciliation của đối tác; chỉ đặt message vào queue bền vững không tự giải quyết bài toán này.

Điều tương tự áp dụng cho gửi email, chuyển tiền, ghi dữ liệu và webhook. Phân biệt:

- **At-most-once attempt:** có thể mất việc, ít trùng hơn.
- **At-least-once delivery:** giảm nguy cơ mất event bằng retry/ack, nhưng event có thể lặp.
- **Exactly-once business effect:** đòi hỏi idempotency/transaction/fencing hoặc thiết kế nghiệp vụ thích hợp qua mọi hệ thống liên quan; không suy ra chỉ vì broker quảng cáo một tính năng giao nhận.

## 9. Java 17 chạy độc lập: hai kiểu phòng vệ nhanh

Để quan sát **từ chối khi executor đầy** và **giới hạn số việc đang chạy**, ví dụ này chỉ dùng JDK, không phụ thuộc Spring. Nó không giả lập durable storage: lưu bền vững phải được chứng minh qua DB/broker và thử restart/crash, không thể chỉ thay tên một `List` trong RAM thành “queue bền vững”.

Lưu toàn bộ vào file **`OverloadDecisionDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class OverloadDecisionDemo {

    static boolean rejectWhenExecutorFull() throws Exception {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);

        try {
            Future<?> running = executor.submit(() -> {
                workerStarted.countDown();
                try {
                    releaseWorker.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!workerStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker was not started");
            }

            // Worker duy nhất đang chờ; task này chiếm 1 vị trí queue.
            Future<?> queued = executor.submit(() -> { });

            boolean rejected = false;
            try {
                executor.execute(() -> { });
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }

            releaseWorker.countDown();
            running.get();
            queued.get();
            return rejected;
        } finally {
            releaseWorker.countDown();
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    static void limitConcurrentAdmissions() {
        Semaphore gate = new Semaphore(2);

        boolean first = gate.tryAcquire();
        boolean second = gate.tryAcquire();
        boolean third = gate.tryAcquire();

        System.out.println(
                "admit=" + first + "," + second + "," + third);

        if (first) {
            gate.release();
        }
        boolean retry = gate.tryAcquire();
        System.out.println("admitAfterRelease=" + retry);

        if (second) {
            gate.release();
        }
        if (retry) {
            gate.release();
        }
        System.out.println("availablePermits=" + gate.availablePermits());
    }

    public static void main(String[] args) throws Exception {
        System.out.println(
                "executorRejected=" + rejectWhenExecutorFull());
        limitConcurrentAdmissions();
    }
}
```

Chạy bằng JDK 17+:

```bash
javac OverloadDecisionDemo.java
java OverloadDecisionDemo
```

**Stdout xác định khi chương trình kết thúc bình thường:**

```text
executorRejected=true
admit=true,true,false
admitAfterRelease=true
availablePermits=2
```

Giải thích:

1. Worker duy nhất bị giữ ở latch, vị trí queue duy nhất đã bị chiếm. Task thứ ba không được nhận, `AbortPolicy` phát `RejectedExecutionException`: `executorRejected=true`. Trong `ThreadPoolTaskExecutor` của Spring, lỗi tương ứng theo contract Spring thường là `TaskRejectedException`.
2. Semaphore có 2 permit; hai lời gọi đầu lấy được, lời gọi thứ ba bị từ chối ngay: `true,true,false`.
3. Sau khi trả một permit, lần thử mới được nhận; cuối cùng trả hết permit đã lấy nên `availablePermits=2`.
4. Trình tự được điều khiển bằng latch nên kết quả **không phụ thuộc** lịch chạy thread khi chạy bình thường; không dùng thời gian sleep để dự đoán kết quả.

**Không nên lấy throughput từ chương trình nhỏ này** để chọn pool production: nó là thử nghiệm tính chất admission/rejection. Khi load test thực tế, bổ sung request traffic, downstream, thời gian chờ, queue age, timeout và trường hợp crash.

## 10. Chọn phản hồi HTTP cho từng tình huống

Một quy tắc thiết kế tiện dụng:

| Tình huống | Phản hồi thường hợp lý | Công việc đã được nhận chưa? |
| --- | --- | --- |
| Tenant hết hạn mức 100 request/phút, chưa tạo job | `429` + mã quota; có thể có `Retry-After` | Chưa |
| CPU/worker pool bão hòa, deadline không thể đáp ứng | `503`; có thể có `Retry-After` | Chưa |
| Semaphore bảo vệ DB đã hết permit | `503` khi lỗi công suất chung, hoặc `429` khi giới hạn riêng caller | Chưa |
| Gửi vào executor RAM thành công, API chỉ cam kết best-effort | Có thể `202` nếu hợp đồng mô tả rõ mức bảo đảm và cách theo dõi | Đã nhận theo **RAM**, có thể mất khi crash |
| DB job + outbox đã commit, công việc sẽ được worker xử lý sau | `202 Accepted` + `Location`/job ID | Đã nhận **bền vững**, chưa hoàn tất |
| DB commit thất bại trước khi xác nhận nhận job | `5xx` phù hợp, không được khẳng định `202` durable | Có thể chưa nhận; cần xử lý trường hợp response không chắc chắn |
| Client retry cùng idempotency key và cùng payload | Trả về cùng job và trạng thái hiện có theo hợp đồng | Không tạo job trùng |
| Client dùng lại cùng key nhưng payload khác | `409 Conflict` hoặc lỗi theo hợp đồng | Không nhận job mới |
| Job xử lý xong nhưng thất bại nghiệp vụ | `GET /jobs/{id}` trả `200` với `FAILED`, hoặc API trạng thái chuyên biệt | Đã nhận trước đó, nay có kết quả thất bại |

**Lưu ý về lỗi không chắc chắn:** đôi khi DB **đã commit** nhưng kết nối giữa DB và API bị lỗi trước khi API thấy kết quả, hoặc response `202` đã gửi nhưng client timeout. Trong trường hợp đó không thể kết luận chắc chắn “chưa nhận”. Cần **idempotency key + tra cứu trạng thái** để client retry an toàn, tránh tạo job lặp.

## 11. Các tình huống lựa chọn chiến lược

### Tình huống A — API gợi ý sản phẩm phải trả trong 200 ms

Nếu tính toán CPU hoặc downstream kéo dài hơn deadline, queue dài sẽ biến câu trả lời thành vô dụng. Chọn **giới hạn số request đang xử lý**, queue rất ngắn hoặc không queue, từ chối khi quá tải. Client có thể dùng cached/fallback response theo hợp đồng; không cần durable job nếu kết quả không còn giá trị khi quay lại sau một phút.

### Tình huống B — Xuất báo cáo kế toán mất 5 phút

Người dùng không cần giữ kết nối HTTP 5 phút; mất yêu cầu sau restart là không chấp nhận. Chọn **lưu job vào DB + outbox/worker**, trả `202` + trạng thái. Vẫn đặt quota theo tenant và backlog limit; khi DB không thể lưu hoặc backlog vượt giới hạn cam kết, trả `429`/`503`.

### Tình huống C — Gửi thông báo marketing số lượng lớn

Các task có thể chạy sau, nhưng rate limit của nhà cung cấp email rất thấp. Chọn durable queue, worker xử lý có tốc độ giới hạn (token bucket/concurrency cap), retry và idempotency. Nếu nhà cung cấp gặp sự cố, không tăng vô hạn worker/queue; dùng circuit breaker, lùi thời gian retry và quản lý TTL của chiến dịch.

### Tình huống D — Đặt hàng còn một sản phẩm

Nếu quá tải dẫn tới hai request cùng đặt thành công, queue không tự bảo vệ bất biến tồn kho. Cần **transaction/conditional update trong DB**, idempotency cho lệnh tạo đơn; chọn synchronous hoặc durable job tùy hợp đồng giao dịch. Không hứa thành công khi mới ghi job: `202` chỉ là accepted, chưa phải xác nhận đã có hàng.

### Tình huống E — Hệ thống nhiều tenant, một khách hàng gây burst

Chọn rate limit per tenant (`429`), bulkhead bảo vệ tài nguyên chung, queue fairness/priority nếu có job bền vững. Giới hạn `Semaphore` cục bộ ở 10 replica phải được tính theo **tổng mức tiếp nhận**; nếu muốn quota 200 job/minute trên toàn hệ thống, cần nguồn đếm và thuật toán phân tán tương ứng.

## 12. Vận hành: lấy tín hiệu quá tải từ đâu?

Đo đồng thời **lưu lượng nhận** và **khả năng hoàn tất**:

- **Request ingress:** rate theo endpoint/tenant, status `429`/`503`/`202`, API p95/p99, timeout và tỷ lệ retry.
- **Executor:** `activeCount`, pool size, queue depth, **tuổi job lâu nhất**, số lần reject, thời gian chờ trước khi chạy, runtime theo loại việc.
- **Downstream:** connection pool active/pending, p95 latency, timeout, rate limit, circuit breaker open count.
- **Durable job:** số `QUEUED`, `RUNNING`, `RETRY_WAIT`, tỷ lệ `SUCCEEDED`/`FAILED`, số lần thử, backlog age, dead-letter, mất heartbeat, outbox lag, thời gian từ `202` đến hoàn tất.
- **Hạ tầng:** CPU throttling, memory, GC pause, file descriptor/socket exhaustion, disk và DB storage.
- **Công bằng:** backlog và rejection theo tenant/priority, tránh một nhóm dùng hết tài nguyên nhóm khác.

Một vài tín hiệu và phản ứng:

| Quan sát | Nguyên nhân có thể | Hành động cần cân nhắc |
| --- | --- | --- |
| Active threads cao, queue không ngừng tăng | Arrival > completion hoặc downstream chậm | Admission/rate limit, giảm work, scale thực sự |
| CPU còn dư, đa số worker chờ JDBC connection | DB pool hoặc query nghẽn | Giới hạn concurrency, tối ưu query, điều chỉnh pool theo DB |
| `503` giảm nhưng p99 tăng mạnh sau khi tăng queue | Đẩy áp lực vào thời gian chờ | Giảm queue theo deadline, báo overload sớm |
| Outbox tăng, broker/worker không nhận | Publisher lỗi, broker không sẵn sàng | Khôi phục publisher, giám sát lag, ngừng nhận vượt quota |
| `FAILED`/retry tăng sau outage | Retry storm hoặc downstream còn yếu | Backoff + jitter, giới hạn retry, circuit breaker |
| Queue gần như trống nhưng CPU quá tải | Worker làm việc CPU-heavy | Giới hạn concurrency CPU, profile code, tránh oversubscription |

**SLO theo từng chiến lược cũng khác:**

- Trả lỗi sớm: xác suất từ chối có chủ đích, thời gian phản hồi từ chối, không để server suy sụp.
- Admission control: tỷ lệ accepted/rejected, thời gian chờ permit và tác động giữa nhóm tải.
- Durable job: tỷ lệ job được nhận vẫn còn sau restart, độ trễ đến khi hoàn tất, độ trễ publish outbox, retry và job mắc kẹt.

Không tối ưu chỉ bằng “tỷ lệ HTTP 2xx cao”. Một API trả hàng nghìn `202` trong khi job không bao giờ chạy có thể tệ hơn việc từ chối sớm đúng lúc.

## 13. Những lỗi thường gặp

| Hiểu sai / triển khai sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| “Queue càng dài càng tốt” | OOM, request quá hạn, độ trễ hàng phút | Hữu hạn, tính theo deadline và throughput |
| `maxPoolSize` rất lớn, nhưng queue không giới hạn | Pool không mở rộng như mong đợi, backlog vẫn tăng | Hiểu queue-before-grow, cấu hình core/max/queue đồng bộ |
| Trả `202` ngay sau `executor.execute()` và gọi là *durable* | Crash làm mất job đã hứa xử lý | Commit job/outbox hoặc durable broker trước `202` |
| Trả `429` cho mọi lỗi backend | Client bị quy lỗi dù server/DB bão hòa | Phân biệt quota caller và overload server |
| `CallerRunsPolicy` cho request CPU-heavy | Request thread chạy task, latency đột biến | Chọn policy theo SLO, có thể dùng `AbortPolicy` + từ chối |
| Bắt mọi exception rồi trả `503` | Che giấu lỗi lập trình/vĩnh viễn | Chỉ map đúng lỗi capacity/overload |
| Retry vô hạn, không jitter | Retry storm, amplifies outage | Retry budget, backoff, deadline, dead-letter |
| Chỉ token bucket mà không giới hạn in-flight | Request ít nhưng xử lý rất lâu vẫn giữ hết worker | Kết hợp concurrency limit và timeout |
| Chỉ semaphore ở mỗi instance khi quota là toàn cụm | Tổng số được nhận vượt quota mong muốn | Phân phối ngân sách hoặc cơ chế rate limit chung |
| Publish message ngoài transaction sau DB commit | Crash giữa bước gây job không được tiêu thụ | Transactional outbox/DB queue |
| Coi message broker mặc định là exactly-once | Side effect bị lặp khi redelivery | Consumer idempotent, deduplication, transaction/fencing |
| Ack trước khi cập nhật trạng thái/xử lý | Crash làm mất trách nhiệm xử lý | Ack theo hợp đồng sau ghi bền vững |
| Không có cơ chế reclaim `RUNNING` sau worker crash | Job kẹt vĩnh viễn | Lease/heartbeat/reconciliation |
| Không phân quyền `GET /jobs/{id}` | Lộ kết quả/metadata của tenant khác | Kiểm tra quyền và scope tenant trên mọi thao tác |
| Dùng test sleep làm sizing production | Ước lượng sai CPU/DB/network | Load test với tải và dependency thực |

## 14. Checklist thiết kế trước khi triển khai

1. **Ghi hợp đồng:** client cần kết quả trong response hiện tại hay có thể nhận `jobId`? Khi nào `202` được phát? Được mất job sau restart không?
2. **Xác định ngân sách:** throughput thực, latency SLO, queue wait, RAM, CPU, DB connections, broker throughput và hạn mức đối tác.
3. **Phân loại overload:** quota per caller → `429`; công suất chung tạm hết → `503`; chỉ `202` khi thực sự nhận được việc.
4. **Đặt rate/concurrency/queue cap:** giới hạn tại nơi tiêu thụ tài nguyên; kiểm soát tổng qua các instance.
5. **Đặt chính sách executor:** core, max, queue, rejection handler, timeout; kiểm tra `CallerRunsPolicy` có chặn request thread không.
6. **Nếu durable:** lưu job và outbox atomically, trả cùng job cho retry có cùng idempotency key, publish với xác nhận, consumer idempotent.
7. **Xử lý crash window:** sau commit trước response, sau publish trước ack, sau side effect trước ghi `SUCCEEDED`, worker chết khi `RUNNING`.
8. **Đặt TTL, retry và hủy:** giữ trạng thái lỗi có thể chẩn đoán, dead-letter, quyền truy cập kết quả và dọn dữ liệu cũ.
9. **Đo và kiểm thử:** tải vượt công suất, burst, DB/broker downtime, restart, nhiều replica, client retry, downstream latency và quota per tenant.
10. **Rà soát bảo mật:** xác thực, phân quyền, payload limit, quota fairness, dữ liệu cá nhân trong job/outbox, secret handling.

## 15. Câu hỏi tự kiểm tra

**1.** API nhận 200 request/giây nhưng chỉ xử lý được 80 request/giây trong hàng giờ. Có nên chỉ tăng queue lên 1 triệu không?  
**Đáp:** Không. Backlog tích lũy và thời gian chờ tăng liên tục. Cần tăng công suất thực, giảm lượng công việc hoặc giới hạn/từ chối nhận.

**2.** Một tenant vượt 20 POST/phút, còn server vẫn khỏe. Trả mã gì?  
**Đáp:** Thường `429 Too Many Requests` kèm mã quota, có thể có `Retry-After` nếu biết mốc thử lại.

**3.** Pool worker bị đầy vì downstream timeout, không còn khả năng nhận tác vụ. Trả mã gì?  
**Đáp:** Thường `503 Service Unavailable` cho overload tạm thời; bảo đảm request bị từ chối chưa bị ghi nhận thành accepted.

**4.** Vì sao một `Semaphore(10)` trong mỗi replica của cụm 6 replica không bảo đảm tổng cùng lúc chỉ có 10 task?  
**Đáp:** Mỗi replica có 10 permit riêng; lý thuyết toàn cụm có thể đạt 60.

**5.** `ThreadPoolTaskExecutor(core=4,max=12,queue=200)` có tăng lên 12 worker trước khi queue đầy không?  
**Đáp:** Thông thường không. Khi đạt core, queue được ưu tiên trước; vượt core khi queue không nhận thêm.

**6.** API trả `202` ngay khi đưa việc vào một queue RAM, sau đó JVM chết. Có đáp ứng yêu cầu “job không được mất” không?  
**Đáp:** Không. Cần durable store hoặc broker với xác nhận phù hợp trước khi nhận trách nhiệm.

**7.** DB ghi job thành công nhưng publish broker thất bại giữa hai bước. Cách tránh “job bị bỏ quên” là gì?  
**Đáp:** Lưu job + outbox trong một DB transaction, dùng publisher phát lại và consumer idempotent; hoặc dùng một durable DB queue/thiết kế khác có recovery rõ ràng.

**8.** Broker gửi cùng message hai lần do crash sau side effect và trước ack. Có thể tránh side effect lặp chỉ bằng cấu hình queue không?  
**Đáp:** Không đủ; phải dùng idempotency key, deduplication và/hoặc transaction/fencing ở ranh giới side effect.

**9.** Có nên gửi `Retry-After: 5` khi không biết service sẽ phục hồi sau 5 giây?  
**Đáp:** Chỉ nên công bố khi có căn cứ; nếu không biết, không bịa thời điểm phục hồi. Client vẫn cần backoff/jitter theo chính sách.

**10.** Job `RUNNING` từ hôm qua, worker đã chết. Vấn đề là gì?  
**Đáp:** Thiếu lease/heartbeat và quy trình reclaim/reconciliation. Durable job không đồng nghĩa tự phục hồi nếu trạng thái bị kẹt.

## 16. Ghi nhớ và tài liệu tham khảo

Ba lựa chọn trả lời ba câu hỏi khác nhau:

- **Trả lỗi sớm:** hệ thống **không nhận** công việc này; client biết có thể retry khi nào/với điều kiện gì. Dùng `429` cho quota/rate limit của caller, `503` cho overload tạm thời của service theo hợp đồng.
- **Hạn chế nhận thêm:** hệ thống chỉ nhận trong giới hạn **rate, concurrency, queue, downstream** có thể phục vụ; khi hết ngân sách phải từ chối rõ ràng.
- **Lưu công việc bền vững:** hệ thống **nhận trách nhiệm xử lý về sau** sau khi ghi nhận an toàn; trả `202` và job ID, có cơ chế trạng thái, retry, dedupe và recovery. Không hứa nghiệp vụ đã hoàn tất.

Các nguồn chính thức:

- [RFC 9110 — 202 Accepted](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.3), [503 Service Unavailable](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.6.4) và [Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3).
- [RFC 6585 — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html#section-4).
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html).
- [Spring Framework — `ThreadPoolTaskExecutor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html).
- [Java SE 17 — `ThreadPoolExecutor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).
- [Java SE 17 — `Semaphore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html).