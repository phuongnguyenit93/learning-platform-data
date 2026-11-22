# Không đồng nhất tác vụ đã được nhận với nghiệp vụ đã hoàn thành

Một ứng dụng Spring nhận yêu cầu tạo báo cáo, gửi email hoặc xử lý đơn hàng, sau đó gọi `executor.execute(task)` hay một phương thức `@Async`. Lệnh giao việc trả về mà không ném lỗi. **Có thể trả ngay “đã xử lý thành công” cho khách hàng không?** Không. Ở thời điểm đó, hệ thống thường mới biết **tác vụ đã được executor nhận**, chứ chưa biết worker đã chạy, xử lý xong, ghi dữ liệu thành công hay nghiệp vụ đã đạt trạng thái cuối.

Đây là một ranh giới rất quan trọng của mô hình xử lý bất đồng bộ trong **Spring Framework – concurrency**, thuộc nhóm **Gửi và nhận tác vụ**. Bài học phân biệt bốn lớp thông tin: **tiếp nhận**, **thực thi**, **kết quả kỹ thuật** và **kết quả nghiệp vụ có thể kiểm chứng**. Từ đó thiết kế API, trạng thái job, xử lý lỗi, retry và khả năng phục hồi đúng kỳ vọng.

## 1. Một task đi qua nhiều trạng thái, không chỉ “thành công/thất bại”

Xét một HTTP request yêu cầu xuất báo cáo:

```text
Client                    Spring API              Executor            Worker / DB / Storage
  |                           |                       |                       |
  | POST /reports             |                       |                       |
  |-------------------------->|                       |                       |
  |                           | submit(task)          |                       |
  |                           |---------------------->|                       |
  |                           |<--- accepted ----------|                       |
  |<--- 202 Accepted + jobId--|                       |                       |
  |                           |                       |-- queue / start ------>|
  |                           |                       |                       | xử lý...
  |                           |                       |                       | ghi file / DB
  | GET /jobs/{id}            |                       |                       |
  |-------------------------->| đọc trạng thái        |                       |
  |<--- RUNNING / SUCCEEDED --|<-----------------------------------------------|
```

**202 Accepted** ở hình là ví dụ cho một API có giao thức job nền. Nó **không có nghĩa tác vụ đã hoàn thành**. Với kết quả chỉ nằm trong RAM, 202 cũng **không mặc nhiên bảo đảm sẽ sống sót qua crash**.

Một mô hình trạng thái thường gặp:

| Trạng thái | Ý nghĩa | Đã hoàn thành nghiệp vụ? |
| --- | --- | --- |
| `NEW` / `VALIDATING` | Kiểm tra dữ liệu, quyền, quota trước lúc nhận | Chưa |
| `ACCEPTED` | Hệ thống xác nhận đã nhận yêu cầu theo hợp đồng được công bố | Chưa |
| `QUEUED` | Task đã vào hàng chờ của executor/queue | Chưa |
| `RUNNING` | Worker đang thực thi | Chưa |
| `RETRYING` | Một lần thử thất bại, đang chuẩn bị thử lại | Chưa |
| `SUCCEEDED` | Điều kiện nghiệp vụ thành công đã được thỏa và có bằng chứng phù hợp | Có, theo hợp đồng nghiệp vụ |
| `FAILED` | Không đạt điều kiện thành công theo chính sách hiện tại | Không |
| `CANCELLED` | Đã hủy thành công theo ý nghĩa mà ứng dụng định nghĩa | Không nhất thiết “hoàn tác” tác động đã xảy ra |
| `EXPIRED` | Quá thời hạn cho phép xử lý/đợi | Chưa chắc tác động bên ngoài chưa xảy ra |

Không bắt buộc mọi hệ thống có tất cả trạng thái. Quan trọng hơn là **mỗi trạng thái có định nghĩa và điều kiện chuyển rõ ràng**. Ví dụ, một job chỉ được chuyển `SUCCEEDED` khi việc lưu báo cáo thực sự hoàn tất và có thể truy xuất được, không phải ngay sau khi caller submit task.

### Bốn câu cần phân biệt

1. **Đã chấp nhận yêu cầu chưa?** API/executor có cho công việc vào hệ thống hay trả lỗi ngay?
2. **Đã bắt đầu thực hiện chưa?** Worker đã lấy task khỏi queue hay chưa?
3. **Đã kết thúc thực thi chưa?** Phương thức `run`/`call` đã hoàn tất bình thường, ném lỗi hay bị hủy?
4. **Nghiệp vụ đã thành công chưa?** Tác động cần thiết như chuyển trạng thái đơn hàng, lưu chứng từ, gửi đúng thông báo hoặc xác nhận thanh toán đã đạt cam kết nghiệp vụ và có thể chứng minh chưa?

Bốn câu này có thể có bốn câu trả lời khác nhau tại cùng một thời điểm.

## 2. `execute` hoặc `submit` trả về thực sự nói gì?

Với một thread pool thông thường:

```java
executor.execute(() -> generateReport(reportId));
```

Khi `execute` trả về bình thường trong cấu hình ném lỗi khi từ chối, điều đó cho biết task đã được chấp nhận theo quy tắc executor, **không chứng minh `generateReport` đã chạy hoặc thành công**. Task có thể đang chờ trong queue. Trong chính sách `CallerRunsPolicy`, task có thể chạy ngay trên caller lúc pool bão hòa; vì vậy cũng không được mặc định “`execute` luôn return ngay”. Còn với handler `DiscardPolicy`, một task bị bỏ có thể không tạo exception, nên phải hiểu **chính sách từ chối cụ thể**, không coi “không throw” là bảo đảm nhận việc trong mọi cấu hình.

Tương tự:

```java
Future<String> future = executorService.submit(() -> generateReport());
```

`submit` thường trả một `Future` đại diện cho kết quả *sẽ có*. Nó không tự chờ worker chạy xong. Để biết kết quả, caller cần quan sát `get()`, `isDone()` và trạng thái exception/cancellation.

**Bảng so sánh:**

| Lệnh/thông tin | Điều biết được | Điều không thể suy ra |
| --- | --- | --- |
| `execute(task)` không ném lỗi, AbortPolicy | Task đã được executor nhận hoặc đã chạy trên cơ chế được cấu hình | Tác động nghiệp vụ đã hoàn thành |
| `submit(callable)` trả `Future` | Có handle để quan sát xử lý | Task đã kết thúc thành công |
| `future.isDone() == true` | Future đã ở trạng thái cuối (có thể hoàn tất, thất bại, hủy) | Nghiệp vụ thành công |
| `future.get()` trả giá trị bình thường | Callable đã trả về bình thường; có quan hệ memory-consistency phù hợp | Giao dịch DB, API ngoài hoặc side effect đã bền vững nếu code chưa bảo đảm |
| `future.get()` ném `ExecutionException` | Task kết thúc với exception được bao bên trong | Tác động bên ngoài chắc chắn chưa xảy ra |
| `CompletableFuture.isCompletedExceptionally()` | Future hoàn tất theo đường lỗi hoặc hủy tùy tình huống | Tác động nghiệp vụ đã được hoàn tác |
| HTTP 202 từ API job | Yêu cầu đã được chấp nhận **theo hợp đồng API** | Công việc đã xử lý xong hoặc sẽ chắc chắn chạy một lần duy nhất |

Đặc biệt, một task có thể thực hiện xong side effect rồi **bị lỗi khi ghi trạng thái kết quả**, khiến hệ thống báo `FAILED` dù side effect thực sự đã xảy ra. Ngược lại, code có thể return bình thường nhưng **chưa kiểm chứng** việc dịch vụ ngoài đã thực hiện yêu cầu.

## 3. Ba tầng “hoàn thành” khác nhau

### 3.1. Hoàn thành ở tầng executor

Worker chạy xong `Runnable.run()` hoặc `Callable.call()`. `Future` chuyển trạng thái cuối. Đây là trạng thái **kỹ thuật của tác vụ**.

```java
CompletableFuture<String> task =
        CompletableFuture.supplyAsync(() -> "done", executor);
```

Ở đây `"done"` chỉ là giá trị mà lambda trả về. Executor không biết từ `"done"` có nghĩa **báo cáo đã lưu thành công** hay không.

### 3.2. Hoàn thành ở tầng ứng dụng

Ứng dụng kiểm tra các bước cụ thể: tạo file, ghi storage, cập nhật DB, nhận response từ downstream, ghi lịch sử tác vụ, v.v. Nếu từng bước trả về thì application có thể đánh giá kết quả theo chính sách của mình.

Tuy nhiên, “gửi HTTP request tới nhà cung cấp email thành công” có thể chỉ nghĩa **nhà cung cấp đã nhận request**. Nó chưa chắc email đã được phát đến hộp thư người nhận. Mỗi hệ thống ngoài có ngữ nghĩa xác nhận khác nhau.

### 3.3. Hoàn thành ở tầng nghiệp vụ

Một yêu cầu tạo báo cáo có thể chỉ được xem là hoàn thành khi:

- File thực sự tồn tại ở nơi lưu trữ dự kiến.
- Metadata/file ID liên kết tới job đã được commit/ghi bền vững.
- Người có quyền có thể tải/tra cứu file theo hợp đồng.
- Trạng thái job được cập nhật theo điều kiện thành công này.

Với nghiệp vụ thanh toán, “đã gửi yêu cầu thanh toán” khác hoàn toàn “ngân hàng/PSP xác nhận giao dịch thành công”. Với nghiệp vụ gửi email, “đã enqueue vào email provider” khác “đã được phát”; có thể có trạng thái riêng như `SUBMITTED_TO_PROVIDER`, `DELIVERED`, `BOUNCED`.

**Nguyên tắc:** định nghĩa `SUCCEEDED` bằng **bằng chứng nghiệp vụ** thay vì bằng việc `executor.execute` return.

## 4. Ví dụ Java 17+ chạy độc lập: accepted ≠ done, done ≠ success

Ví dụ sau dùng JDK 17+ để minh họa rõ hai sự tách biệt. Một task được `submit` thành công nhưng còn đang chờ phép giải phóng có kiểm soát; một task khác **đã kết thúc nhưng kết thúc bằng exception**.

Lưu nội dung thành **AcceptedVsCompletedDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;

public class AcceptedVsCompletedDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean businessStepFinished = new AtomicBoolean(false);

        try {
            Future<?> accepted = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
                businessStepFinished.set(true);
            });

            started.await();
            System.out.println("accepted=true, done="
                    + accepted.isDone()
                    + ", businessStepFinished="
                    + businessStepFinished.get());

            release.countDown();
            accepted.get();
            System.out.println("accepted=true, done="
                    + accepted.isDone()
                    + ", businessStepFinished="
                    + businessStepFinished.get());

            Future<?> failed = pool.submit(() -> {
                throw new IllegalStateException("simulated failure");
            });
            try {
                failed.get();
            } catch (ExecutionException ex) {
                System.out.println("failedFutureDone="
                        + failed.isDone()
                        + ", taskSucceeded=false");
            }
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac AcceptedVsCompletedDemo.java
java AcceptedVsCompletedDemo
```

**Stdout xác định khi chương trình chạy bình thường:**

```text
accepted=true, done=false, businessStepFinished=false
accepted=true, done=true, businessStepFinished=true
failedFutureDone=true, taskSucceeded=false
```

**Vì sao kết quả đáng tin?**

1. `pool.submit(...)` trả về một `Future`. `started.await()` bảo đảm worker đã bắt đầu task nhưng vẫn bị giữ tại `release.await()`.
2. Khi latch chưa mở, task chưa thể chạy đến dòng đặt `businessStepFinished=true`; `Future.isDone()` là `false`. Việc đã nhận task **không bằng** việc hoàn thành.
3. Sau `release.countDown()`, `Future.get()` chờ tác vụ kết thúc và cho caller quan sát lần ghi vào `AtomicBoolean`. Khi ấy cả `done` và cờ mô phỏng đều `true`.
4. Task thứ hai cố tình ném `IllegalStateException`. `failed.get()` ném `ExecutionException`; Future đã `done=true` nhưng **không phải success**.
5. `CountDownLatch` loại bỏ sự may rủi khi đo trạng thái. Không dùng `Thread.sleep(100)` để đoán chắc worker đã chạy tới đâu.

**Giới hạn cố ý của demo:** biến `businessStepFinished` là một cờ **trong bộ nhớ**, chỉ mô phỏng việc hoàn thành. Nó không chứng minh database đã commit hoặc email đã tới người nhận. Trong ứng dụng thật, trạng thái nghiệp vụ phải dựa trên thao tác kiểm chứng tương ứng.

## 5. `@Async` của Spring và ý nghĩa của kết quả Future

Spring hỗ trợ thực thi method bất đồng bộ qua `@EnableAsync` và `@Async`:

```java
@Service
class ReportService {
    @Async("reportExecutor")
    public CompletableFuture<String> generateReport(String reportId) {
        String url = calculateAndStoreReport(reportId);
        return CompletableFuture.completedFuture(url);
    }

    private String calculateAndStoreReport(String reportId) {
        // Fragment: cần cài đặt nghiệp vụ và lưu trữ thực tế.
        return "/reports/" + reportId;
    }
}
```

Đây là **fragment minh họa**, không phải chương trình hoàn chỉnh: import và executor bean được giả định tồn tại; `calculateAndStoreReport` ở đây chỉ trả chuỗi, **không lưu file thật**. Nó giúp hiểu cách Spring proxy tạo một lời gọi bất đồng bộ và trả kết quả khi method chạy xong.

Khi bean khác gọi `reportService.generateReport(id)` qua Spring proxy, một task được giao cho `reportExecutor`. Caller nhận một `CompletableFuture` để quan sát; điều đó **không tự làm cho báo cáo có thật**. Khi method return bình thường, future đại diện cho completion của đường thực thi Spring, nhưng **ngữ nghĩa nghiệp vụ** vẫn phụ thuộc phần code đã làm và giao dịch/tài nguyên bên ngoài.

**Những điểm dễ sai:**

- Trong cấu hình proxy mặc định, `this.generateReport(id)` được gọi từ chính bean đó thường **không đi qua proxy `@Async`**. Không dựa vào self-invocation để suy luận executor có nhận task hay không.
- `@Async void` không cung cấp Future cho caller, nên không thích hợp nếu caller phải biết kết quả. Exception với kiểu return `void` cần `AsyncUncaughtExceptionHandler` và logging/monitoring phù hợp.
- Khi return `CompletableFuture<T>`, phải quan sát `whenComplete`, `handle`, `exceptionally` hoặc `join/get` tại vị trí thích hợp; nếu không kiểm tra, task lỗi có thể trôi qua trong log mà người dùng vẫn thấy “thành công”.
- `@Async` dùng worker khác không làm JDBC/HTTP blocking trở thành non-blocking. Worker vẫn bận chờ I/O và executor có thể bão hòa.
- Nếu dùng `CallerRunsPolicy` để xử lý overload, tác vụ có thể thực thi trên thread gọi khi pool đầy; còn với `AbortPolicy`, giao việc có thể thất bại ngay với `TaskRejectedException`.
- Future trong một JVM không phải job state bền vững sau restart và không thể hiện tự động trạng thái trên các replica khác.

### 5.1. Future đã hoàn tất nhưng transaction đã commit chưa?

Không nên đánh đồng “method return” với “dữ liệu đã được commit” khi giao dịch và proxy/side effect không nằm trong cùng điều kiện kiểm chứng. Ví dụ một method transactional ghi database rồi **phát tín hiệu `SUCCEEDED` ra ngoài ngay trong method**, trước khi transaction thực sự commit. Nếu transaction rollback khi kết thúc, tín hiệu đã phát sẽ là sai.

Cách an toàn hơn tùy thiết kế:

1. **Trạng thái job và kết quả nghiệp vụ trong cùng transaction DB:** commit thành công rồi dữ liệu mới hiển thị cho reader. Nếu rollback, cả hai cùng rollback.
2. **Có hoạt động ngoài DB:** sau khi xác nhận hoạt động đó theo contract của provider, mới đánh dấu thành công; phải dự kiến kết quả không chắc chắn khi timeout.
3. **Sự kiện chỉ được phát sau commit:** có thể dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` cho event trong tiến trình khi phù hợp, nhưng event listener in-memory có thể mất khi crash. Với yêu cầu bền vững nên dùng transactional outbox/broker.
4. **Nếu trạng thái completion được kiểm chứng bên ngoài:** chỉ chuyển `SUCCEEDED` khi có chứng cứ đủ mạnh, chẳng hạn báo cáo đã nằm trong object storage và metadata đã nhất quán.

Không có annotation nào của Spring tự động biến một chuỗi DB + HTTP + broker thành một giao dịch nguyên tử trên mọi hệ thống.

## 6. HTTP 202 Accepted và job API: trả lời thật đúng điều đã làm

Khi API nhận việc cần xử lý nền, có thể dùng:

```http
POST /jobs HTTP/1.1
Content-Type: application/json

{"reportType":"monthly"}
```

Nếu API đã nhận yêu cầu **theo hợp đồng** và cung cấp đường theo dõi, một response thường là:

```http
HTTP/1.1 202 Accepted
Location: /jobs/8f2a

{"jobId":"8f2a","statusUrl":"/jobs/8f2a"}
```

Client sau đó truy vấn:

```http
GET /jobs/8f2a HTTP/1.1
```

Có thể nhận:

```json
{"jobId":"8f2a","state":"RUNNING","message":"Generating report"}
```

Và về sau:

```json
{"jobId":"8f2a","state":"SUCCEEDED","message":"Report stored"}
```

**Đây là giao thức minh họa**, không phải log của một server đang chạy. Cách đặt trạng thái, payload và đường dẫn cần được thiết kế theo hợp đồng thực tế.

### Không dùng 200, 201, 202 thay thế tùy tiện

- **200 OK:** chỉ phản ánh request HTTP thành công theo response hiện tại; nếu body tuyên bố “báo cáo xong”, chỉ nên trả sau khi điều kiện thành công thực sự đã được kiểm chứng.
- **201 Created:** có thể nói một **tài nguyên job** đã được tạo, nhưng không có nghĩa *bản báo cáo* đã tạo xong. Phân biệt đối tượng “job” với kết quả của job.
- **202 Accepted:** chuẩn HTTP mô tả yêu cầu đã được chấp nhận để xử lý nhưng **chưa hoàn tất tại thời điểm phản hồi**; nó mang tính **noncommittal**, không phải cam kết tiến trình cuối cùng chắc chắn sẽ thành công.
- **400/422:** request không hợp lệ theo yêu cầu API.
- **429 Too Many Requests:** ứng dụng áp dụng giới hạn tốc độ/quota của client.
- **503 Service Unavailable:** backend tạm không có capacity/không tiếp nhận được công việc; cân nhắc `Retry-After` nếu có chính sách retry.
- **404 Not Found khi GET status:** có thể là job không tồn tại, bị xóa hết thời hạn hoặc client đang truy cập nhầm replica của hệ thống in-memory. Phải xác định ý nghĩa cụ thể trong API.

Không trả 202 nếu thực tế **chưa chấp nhận task** (executor từ chối hoặc lưu job thất bại), trừ khi hệ thống đã đưa nó vào một cơ chế tiếp nhận thay thế hợp lệ và có thể theo dõi được.

### Trường hợp client timeout sau khi server đã nhận

Client gửi POST, server enqueue thành công, nhưng mạng đứt trước khi response 202 tới client. Client nghĩ “không biết đã nhận hay chưa” rồi retry. Nếu mỗi POST tạo một job mới, báo cáo/email có thể bị xử lý **hai lần**. Cần **idempotency key** hoặc request ID ổn định để lần gửi lại có thể tìm kết quả của lần đầu.

Đó là lý do **nhận được HTTP response** và **server đã nhận việc** cũng có thể là hai góc nhìn khác nhau khi mạng lỗi.

## 7. Spring Boot 3.x: API báo “đã nhận” và cho tra trạng thái

Ví dụ sau dùng **Java 17+**, Spring Boot 3.x/Spring Framework 6.x và dependency `spring-boot-starter-web`. Mục đích là thể hiện **cách nói đúng về accepted vs completed** với `ThreadPoolTaskExecutor` và trạng thái job.

**Chú ý:** ví dụ dùng `ConcurrentHashMap` để lưu status **chỉ trong RAM**, nên không bảo đảm bền vững hoặc hoạt động trên nhiều replica. Nó mô phỏng công việc bằng `Thread.sleep`; `SUCCEEDED` chỉ nói rằng phần demo kết thúc bình thường, **không có báo cáo thật được lưu**. Phần 8 giải thích cách nâng cấp lên thiết kế production.

Đặt toàn bộ nội dung trong **src/main/java/com/example/demo/JobApplication.java**:

```java
package com.example.demo;

import java.net.URI;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JobApplication {
    public static void main(String[] args) {
        SpringApplication.run(JobApplication.class, args);
    }

    @Bean("jobExecutor")
    ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("job-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}

record JobReceipt(String jobId, String statusUrl) {}

record JobStatus(String jobId, String state, String message) {}

@Service
class JobService {
    private final ThreadPoolTaskExecutor executor;
    private final ConcurrentMap<String, JobStatus> jobs =
            new ConcurrentHashMap<>();

    JobService(@Qualifier("jobExecutor") ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    JobReceipt submit() {
        String id = UUID.randomUUID().toString();
        jobs.put(id, new JobStatus(id, "QUEUED", "Waiting for a worker"));

        try {
            executor.execute(() -> perform(id));
        } catch (TaskRejectedException rejected) {
            jobs.remove(id); // Không báo accepted cho task bị từ chối.
            throw rejected;
        }

        return new JobReceipt(id, "/jobs/" + id);
    }

    Optional<JobStatus> find(String id) {
        return Optional.ofNullable(jobs.get(id));
    }

    private void perform(String id) {
        jobs.put(id, new JobStatus(id, "RUNNING", "Demo work started"));
        try {
            Thread.sleep(300); // Mô phỏng xử lý, không lưu dữ liệu thật.
            jobs.put(id, new JobStatus(
                    id, "SUCCEEDED", "Demo step finished"));
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            jobs.put(id, new JobStatus(id, "FAILED", "Interrupted"));
        } catch (RuntimeException ex) {
            jobs.put(id, new JobStatus(id, "FAILED", "Processing error"));
        }
    }
}

@RestController
class JobController {
    private final JobService service;

    JobController(JobService service) {
        this.service = service;
    }

    @PostMapping("/jobs")
    public ResponseEntity<?> create() {
        try {
            JobReceipt receipt = service.submit();
            return ResponseEntity.accepted()
                    .location(URI.create(receipt.statusUrl()))
                    .body(receipt);
        } catch (TaskRejectedException rejected) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(Map.of("error", "executor_unavailable"));
        }
    }

    @GetMapping("/jobs/{id}")
    public ResponseEntity<JobStatus> status(@PathVariable String id) {
        return service.find(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
```

Chạy bằng build của project Spring Boot:

```bash
./gradlew bootRun
curl -i -X POST http://localhost:8080/jobs
```

Trên Windows có thể dùng `gradlew.bat bootRun`. Khi executor nhận việc, response có **202 Accepted**, body JSON chứa `jobId` và `statusUrl`, ví dụ:

```json
{"jobId":"b610d4e5-8891-48b1-a63f-632faf38b7cf","statusUrl":"/jobs/b610d4e5-8891-48b1-a63f-632faf38b7cf"}
```

Đây là **ID ví dụ**, không phải ID thực tế cố định. Lấy ID trả về để truy vấn:

```bash
curl -i http://localhost:8080/jobs/<jobId>
```

`<jobId>` trong lệnh trên là **chỗ điền ID thật**, không gõ dấu ngoặc góc trong shell. JSON có thể cho thấy `QUEUED`, `RUNNING` hoặc `SUCCEEDED` tùy thời điểm. Không dự đoán thứ tự log/thread scheduling của từng request. Nếu executor từ chối ngay tại `execute`, API trả **503** với `executor_unavailable`.

### Vì sao ví dụ này không “báo thành công sớm”?

- `submit()` tạo một bản ghi trạng thái `QUEUED` **trước** khi gọi executor, để worker bắt đầu rất nhanh vẫn có record tương ứng.
- Nếu `execute` ném `TaskRejectedException` với `AbortPolicy`, record được xóa và controller không trả 202.
- Nếu được nhận, controller chỉ trả **202 + jobId**, không báo `SUCCEEDED`. Worker tự chuyển `RUNNING` và `SUCCEEDED` sau khi phần demo hoàn thành.
- Nếu worker kết thúc trước khi response HTTP 202 tới client, status GET có thể đã là `SUCCEEDED`. Điều đó **không khiến 202 thành tuyên bố kết quả nghiệp vụ**; response vẫn chỉ xác nhận giao việc theo hợp đồng.
- `ConcurrentHashMap` bảo vệ thao tác đọc/ghi status giữa HTTP thread và worker. Các `JobStatus` là record immutable; không cho caller sửa bản ghi nội bộ.
- Đây là ví dụ **best-effort in-memory**. `jobs` không lưu sau restart, không chia sẻ giữa các server. `SUCCEEDED` ở đây **chỉ là thành công của bước giả lập**.

**Giới hạn cần biết trong hệ thống thật:** Controller trả 202 sau khi `execute` đã nhận vào pool RAM; nếu JVM crash ngay sau đó, job và status đều mất. Muốn bảo đảm nhận việc bền vững, phải thay phần tiếp nhận bằng một transaction/persistent queue phù hợp trước khi trả 202.

## 8. Nâng cấp lên giao thức job bền vững

Giải pháp production thường cần một **job store** có transaction và một worker có khả năng retry. Một thiết kế phổ biến:

```text
Client
  |
  | POST /jobs + Idempotency-Key
  v
API: kiểm tra quyền, payload, quota
  |
  | BEGIN DB transaction
  |   INSERT job(id, status=ACCEPTED, requestHash, ...)
  |   INSERT outbox(jobId, event=JobAccepted, ...)
  | COMMIT
  v
HTTP 202 + jobId
  |
  | outbox publisher (có thể chạy lại)
  v
Message broker / durable queue
  |
  | worker nhận (có thể nhận lặp)
  v
Xử lý nghiệp vụ idempotent
  |
  | Lưu kết quả + trạng thái terminal trong transaction phù hợp
  v
SUCCEEDED / FAILED / RETRYING
  |
  | GET /jobs/{id}
  v
Client thấy trạng thái có thể kiểm chứng
```

### 8.1. Vì sao phải commit trước khi trả accepted?

Nếu chỉ lưu job trong RAM rồi trả 202, một crash có thể làm mất yêu cầu. Nếu lưu database nhưng trả 202 **trước khi transaction commit**, transaction có thể rollback sau response. Vì thế, hợp đồng “đã tiếp nhận bền vững” phải được phát ra **sau một commit thành công**.

Tùy định nghĩa của API, 202 có thể chỉ mang nghĩa best-effort nhận vào RAM. Điều đó không trái với giao thức HTTP nhưng phải minh bạch; không tự hứa “được xử lý chắc chắn” nếu không có cơ chế bảo đảm.

### 8.2. Vì sao cần transactional outbox?

Một lỗi hai bước điển hình:

1. API commit bản ghi job ở database.
2. API cố gửi message đến broker nhưng chết giữa hai bước.

Lúc này DB có job, nhưng broker chưa nhận event. Đảo thứ tự lại (publish trước rồi commit DB) cũng có cửa sổ lỗi: worker nhận event trước khi job tồn tại hoặc transaction rollback.

**Transactional outbox** ghi job + bản ghi event trong **cùng một DB transaction**. Một publisher riêng đọc outbox và gửi đi; có thể gửi lặp khi ack không chắc chắn, nên **consumer phải idempotent**. Outbox không tự tạo exactly-once end-to-end nhưng thu hẹp cửa sổ “DB có job mà không có dấu vết để tiếp tục publish”.

### 8.3. Hoàn tất thực sự ở đâu?

Trong worker, trạng thái `SUCCEEDED` nên được ghi **sau khi hoặc cùng lúc** các điều kiện thành công có bằng chứng:

- Với update DB đơn lẻ, ghi kết quả nghiệp vụ và job status trong cùng transaction khi khả thi.
- Với tạo file ngoài DB, chỉ công bố thành công khi upload được xác nhận theo hợp đồng storage và metadata liên kết với job đã được ghi an toàn. Phải dự phòng trường hợp upload thành công nhưng cập nhật DB thất bại.
- Với gửi mail qua provider, phân biệt provider **chấp nhận request** và **giao email đến người nhận**; trạng thái có thể cần nhiều tầng xác nhận.
- Với thanh toán, không suy luận thành công chỉ từ timeout hay HTTP response chưa đủ; cần đối soát provider transaction ID/trạng thái cuối, và idempotency cho thao tác có tác động tài chính.

**Đừng ghi `SUCCEEDED` trước side effect quan trọng**, sau đó kỳ vọng rollback tự động sửa mọi hệ thống ngoài DB. Nếu side effect đã xảy ra rồi ghi status thất bại, worker retry có thể lặp tác động — phải thiết kế idempotency hoặc compensation tương ứng.

## 9. Retry, lỗi và idempotency

Một tác vụ được nhận có thể thử xử lý nhiều lần. Các lý do phổ biến:

- Worker crash sau khi gọi API ngoài thành công nhưng **trước khi ghi trạng thái hoàn tất**.
- Broker redeliver vì chưa nhận ack.
- Timeout làm caller không biết thao tác ngoài đã xảy ra chưa.
- Người dùng gửi lại POST vì không nhận được response 202.
- Job quá thời hạn hoặc worker được scale/restart.

**At-least-once delivery** nghĩa là một task có thể được gửi/xử lý **nhiều lần**. Mục tiêu đúng thường là **hiệu ứng nghiệp vụ không bị nhân đôi**, không phải khẳng định executor chỉ chạy callback đúng một lần trên toàn hệ thống.

### 9.1. Idempotency key khi nhận job

Client gửi cùng `Idempotency-Key` cho các lần retry của **cùng một yêu cầu logic**. API lưu khóa với request hash và job ID trong DB có unique constraint. Nếu key đã tồn tại và payload trùng, trả lại cùng job ID/trạng thái; nếu key trùng nhưng payload khác, trả lỗi conflict theo hợp đồng.

```text
POST /jobs + key=abc, payload=P → job-123, HTTP 202
Mạng đứt trước khi client nhận response.
POST /jobs + key=abc, payload=P → job-123 (không tạo job thứ hai)
POST /jobs + key=abc, payload=Q → conflict (không tự dùng lại job khác nội dung)
```

Đừng chỉ dùng một `ConcurrentHashMap` in-memory làm kho idempotency cho hệ thống có nhiều replica, vì mỗi replica không nhìn thấy khóa của replica khác.

### 9.2. Idempotency ở worker

Ngay cả khi nhận request chỉ tạo một job, broker vẫn có thể redeliver cùng message. Worker nên dùng khóa ổn định như `jobId`/`paymentIntentId` và guard hiệu ứng nghiệp vụ:

- Kiểm tra trạng thái/deduplication trong transaction.
- Dùng unique constraint hoặc optimistic locking cho thao tác cần đúng một lần về mặt DB.
- Gửi idempotency key đến dịch vụ ngoài nếu provider hỗ trợ.
- Thiết kế retry với exponential backoff, jitter và số lần thử tối đa.
- Đưa nhiệm vụ không thể hoàn tất sang `FAILED` hoặc dead-letter/reconciliation, có công cụ vận hành xử lý.

**Không coi “exactly-once execution” là mặc định của `@Async`, executor hoặc message broker.** Trong thực tế, cần bảo đảm ở cấp **hiệu ứng nghiệp vụ**.

## 10. Khi nào được thông báo “thành công”?

Một quy tắc thực tiễn: thông báo phải phản ánh **điều chắc chắn nhất mà hệ thống đã kiểm chứng**, không phải điều muốn xảy ra.

| Tình huống | Thông báo đúng | Thông báo dễ gây hiểu nhầm |
| --- | --- | --- |
| `executor.execute` nhận task | “Đã nhận tác vụ để xử lý” | “Đã xử lý xong” |
| Task được đưa vào queue bền vững | “Đã ghi nhận yêu cầu, có thể theo dõi bằng job ID” | “Kết quả đã sẵn sàng” |
| Worker bắt đầu tạo báo cáo | “Đang xử lý” | “Báo cáo đã tạo” |
| Worker gửi request sang email provider, provider nhận | “Nhà cung cấp đã nhận yêu cầu gửi” | “Người nhận đã đọc email” |
| File tạo xong, truy cập được và trạng thái commit | “Báo cáo đã sẵn sàng” | Không cần trì hoãn vô cớ |
| `Future.isDone()==true` nhưng Future thất bại | “Xử lý thất bại” | “Hoàn thành thành công” |
| Task được nhận nhưng JVM crash trước khi xử lý | “Trạng thái cần khôi phục/đối soát” | “Thành công” |
| Worker timeout sau khi gọi dịch vụ ngoài | “Chưa xác định, đang kiểm tra trạng thái” | “Chắc chắn thất bại, thử lại ngay” |

Phải xác định *đối tượng của từ “thành công”*: thành công khi **nhận lệnh**, khi **gửi tới provider**, khi **provider thực hiện**, hay khi **khách hàng nhận được kết quả**. Một hệ thống có thể có nhiều trạng thái success khác nhau và không thể thay bằng một boolean mơ hồ.

## 11. Race condition và sự nhất quán trạng thái

Thiết kế job tracking cần đối mặt concurrency thực tế:

### 11.1. Worker bắt đầu trước khi API trả 202

Executor có thể chạy task ngay sau khi submit. Vì vậy, đừng đặt job record **sau** khi submit mà giả định worker chưa chạy. Trong ví dụ Spring, trạng thái `QUEUED` được lưu trước `execute`, sau đó worker cập nhật `RUNNING`. Trả 202 chỉ xác nhận acceptance, dù trạng thái đã tiến tới `RUNNING` hoặc `SUCCEEDED` trước khi response đến client.

### 11.2. Trạng thái có thể bị ghi lùi

Nếu nhiều retry worker và callback cùng sửa một record, có thể xuất hiện:

```text
Worker A: ghi SUCCEEDED
Worker B cũ: ghi RUNNING hoặc FAILED
=> trạng thái bị lùi hoặc ghi đè success
```

Với database, sử dụng **conditional updates**, version/optimistic locking, lease/attempt ID và transition rules. Ví dụ chỉ cho `RUNNING → SUCCEEDED` nếu đúng worker/attempt đang giữ lease, và không cho `SUCCEEDED → RUNNING` do callback cũ.

### 11.3. Trạng thái terminal không đồng nghĩa không còn side effect

Một client gửi cancel khi task đang gọi API ngoài. Worker có thể bị interrupt hoặc Future bị cancel, nhưng HTTP request đã rời hệ thống và provider vẫn xử lý. Do đó **`CANCELLED` không tự bảo đảm các tác động bên ngoài đã bị hoàn tác**. Cần định nghĩa cancellation best-effort và compensation nếu nghiệp vụ yêu cầu.

### 11.4. Multi-instance và visibility

Nếu API có hai replica A/B mà trạng thái job nằm trong memory của A, request `GET /jobs/{id}` đi vào B có thể trả 404 dù job đang chạy ở A. Muốn status nhất quán giữa các replica, dùng shared DB/cache phù hợp, có định nghĩa TTL, version, retention và quyền truy cập.

## 12. Kết quả “đã xong” phải quan sát được

Ngoài trạng thái `SUCCEEDED`, API nên cung cấp đầu ra có thể dùng:

```json
{
  "jobId": "job-123",
  "state": "SUCCEEDED",
  "result": {
    "reportId": "report-456",
    "downloadUrl": "/reports/report-456/download"
  }
}
```

Ví dụ trên là **hợp đồng gợi ý**, không phải response của Spring sample. Chỉ công bố `downloadUrl` khi tài nguyên có thể truy cập theo quyền của caller.

Với `FAILED`, cung cấp mã lỗi/loại lỗi có thể xử lý mà không lộ stack trace hoặc bí mật nội bộ:

```json
{
  "jobId": "job-123",
  "state": "FAILED",
  "error": {
    "code": "REPORT_SOURCE_UNAVAILABLE",
    "retryable": true
  }
}
```

Nên phân biệt lỗi **retryable** (dịch vụ ngoài tạm thời quá tải) với lỗi **permanent** (request không hợp lệ). Không để client tự retry những tác động có thể gây trùng nếu chưa có idempotency.

## 13. Quan sát và vận hành: số “accepted” không phải throughput thành công

Một dashboard chỉ có metric `jobs_submitted_total` sẽ dễ tạo cảm giác hệ thống đang hoạt động tốt dù queue đầy và kết quả nghiệp vụ chậm.

Các chỉ số cần tách:

| Metric | Giải thích |
| --- | --- |
| Requests received | API đã nhận bao nhiêu HTTP request |
| Jobs accepted | Bao nhiêu job được chấp nhận theo hợp đồng API |
| Jobs rejected | Bao nhiêu lần không tiếp nhận do overload/shutdown/validation |
| Jobs started | Bao nhiêu job thực sự được worker bắt đầu |
| Jobs completed successfully | Bao nhiêu job đạt điều kiện thành công nghiệp vụ |
| Jobs failed/cancelled/expired | Các kết thúc không thành công |
| Queue depth/age | Có bao nhiêu task đang chờ, task lâu nhất chờ bao lâu |
| Queue wait duration | Thời gian từ accepted đến started |
| Processing duration | Thời gian từ started đến terminal state |
| End-to-end completion latency | Thời gian từ client gửi yêu cầu đến kết quả có thể dùng |
| Retry count/duplicates | Tỷ lệ xử lý lại, tác động của idempotency |
| “Stuck” jobs | Job quá SLA vẫn `QUEUED` hoặc `RUNNING`, cần recovery |

Một số invariant có thể sử dụng cho **đối soát định kỳ** sau khi quy định rõ cách tính và tránh double counting retry:

```text
Accepted jobs (một job ID duy nhất)
≈ Active jobs + Terminal jobs + Jobs đang cần đối soát

Terminal = SUCCEEDED | FAILED | CANCELLED | EXPIRED (theo contract)
```

Đây chỉ là cách nhìn kiểm toán ở mức job logic, **không phải phép cộng tức thời tuyệt đối** trong hệ thống phân tán có eventual consistency, retry, job deletion và các trạng thái trung gian.

Cần đo cả tỷ lệ hoàn thành theo SLA, tuổi của task cũ nhất trong queue, độ trễ DB/broker và phần trăm request sau khi nhận việc đã cho kết quả cuối. Một hệ thống có 10.000 job accepted nhưng 9.000 job chưa hề hoàn thành chưa thể được mô tả là “đã xử lý thành công 10.000 công việc”.

## 14. Lỗi phổ biến

**Lỗi 1 — Trả “đã gửi email” ngay sau `@Async` submit.** Đúng hơn: “đã nhận yêu cầu gửi”; trạng thái giao email cần nguồn xác nhận riêng.

**Lỗi 2 — `Future.isDone()==true` nên đặt `SUCCEEDED`.** Future có thể bị cancel hoặc failed. Kiểm tra kết quả `get()/join()`, exception và điều kiện nghiệp vụ.

**Lỗi 3 — Method trả về bình thường nên tin mọi side effect đã commit.** Giao dịch có thể chưa commit; provider có thể chỉ trả acknowledgment ban đầu. Bằng chứng thành công phải đúng ranh giới.

**Lỗi 4 — 202 nghĩa bảo đảm thực hiện.** HTTP 202 chỉ nói yêu cầu được chấp nhận để xử lý; mức bảo đảm sống sót qua crash phụ thuộc kiến trúc.

**Lỗi 5 — Executor nhận task vào RAM queue nên coi là durable.** Queue mất khi tiến trình chết; cần DB/broker/outbox cho công việc quan trọng.

**Lỗi 6 — Client timeout thì gửi lại POST mới không có idempotency key.** Có thể sinh hai job cho cùng một yêu cầu logic và gây tác động trùng.

**Lỗi 7 — Worker retry mà không bảo vệ side effect.** Task có thể hoàn thành một phần rồi crash; lần retry có thể tạo thêm báo cáo, thu tiền hoặc gửi email lần hai.

**Lỗi 8 — Cập nhật trạng thái `SUCCEEDED` trước khi ghi file/commit DB.** Trạng thái có thể sai nếu thao tác tiếp theo thất bại hoặc rollback.

**Lỗi 9 — Không cho client truy vấn status.** Response “đã nhận” không có job ID hoặc URL tra cứu khiến không thể biết kết quả cuối.

**Lỗi 10 — Tất cả lỗi dùng chung status `FAILED`.** Không phân biệt retryable/permanent/unknown, mất khả năng recovery hoặc tự động retry hợp lý.

**Lỗi 11 — Một job state in-memory trên nhiều replica.** GET status có thể đi nhầm instance và 404; cần shared job store.

**Lỗi 12 — Không giới hạn backlog và không xử lý rejection.** “Đã nhận” có thể trở thành “xếp hàng vô hạn”; có thể trả 503/429 khi không còn capacity.

**Lỗi 13 — Không thu thập callback error của `@Async`.** Future thất bại sau khi HTTP response đã gửi; cần có trạng thái lỗi, log/metric và cơ chế thông báo.

**Lỗi 14 — Nhầm `CANCELLED` với rollback tác động ngoài.** Interrupt/cancel không thể tự động lấy lại email đã gửi hoặc đảo một giao dịch ngoài hệ thống.

## 15. Checklist thiết kế một API nhận tác vụ

1. Xác định rõ **tiêu chí nghiệp vụ hoàn thành**: điều kiện nào mới cho phép báo `SUCCEEDED`.
2. Định nghĩa **hợp đồng acceptance**: chỉ chấp nhận vào RAM hay đã ghi bền vững? Response phải phản ánh điều đã xảy ra.
3. Cung cấp **job ID**, trạng thái và đường tra cứu; phân biệt queued/running/succeeded/failed.
4. Tách **submit error** (`TaskRejectedException`, validation) khỏi **execution error** (worker exception) và **business failure** (điều kiện nghiệp vụ chưa đạt).
5. Dùng `Future`/`CompletableFuture` để quan sát completion trong JVM, nhưng không coi Future là job store phân tán.
6. Nếu có DB transaction, **không công bố success trước commit**; nếu có broker, cân nhắc transactional outbox.
7. Bảo đảm **idempotency** từ request đến worker khi client retry, broker redeliver hoặc task chạy lại.
8. Đặt timeout, retry/backoff, dead-letter/reconciliation, TTL và quyền truy cập job status rõ ràng.
9. Theo dõi riêng số **accepted**, **started**, **completed**, **failed**, **rejected** và độ trễ end-to-end.
10. Kiểm thử các cửa sổ lỗi: crash sau accepted, crash sau side effect nhưng trước ghi status, transaction rollback, client timeout và concurrent retry.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Controller gọi `executor.execute(task)` và không ném lỗi. Có thể trả HTTP 200 với body `{"status":"COMPLETED"}` không?

**Đáp án:** Chỉ khi nghiệp vụ thực sự đã thỏa điều kiện hoàn thành và đã được kiểm chứng. Việc giao task không lỗi thông thường chỉ chứng minh được acceptance theo policy, không đủ để công bố completed.

**Câu 2.** `Future.isDone()==true` nhưng `future.get()` ném `ExecutionException`. Kết luận gì?

**Đáp án:** Task đã đi đến trạng thái cuối, nhưng thực thi thất bại. Không được coi là thành công nghiệp vụ.

**Câu 3.** Client nhận HTTP 202 từ API ghi task vào in-memory executor. Nếu server crash ngay sau đó, task có chắc được chạy lại?

**Đáp án:** Không. Queue RAM và status in-memory không có cơ chế phục hồi bền vững. Muốn bảo đảm cần persistent job store/broker và retry.

**Câu 4.** Worker gửi lệnh chuyển tiền, network timeout, không rõ provider đã thực hiện chưa. Có thể lập tức đánh dấu `FAILED` và thử lại không?

**Đáp án:** Không nên suy ra chắc chắn giao dịch chưa xảy ra. Cần tra cứu provider status bằng khóa ổn định, áp idempotency và reconciliation để tránh chuyển tiền hai lần.

**Câu 5.** Vì sao `@Async void` không phù hợp khi cần theo dõi job kết quả?

**Đáp án:** Caller không nhận Future kết quả; lỗi có thể đi qua `AsyncUncaughtExceptionHandler`. Cần một cơ chế status bền vững hoặc trả kiểu Future khi phù hợp.

**Câu 6.** Khi worker chuyển job sang `SUCCEEDED` trước khi transaction DB commit, điều gì có thể sai?

**Đáp án:** Nếu transaction rollback, consumer đã thấy thông báo thành công giả. Đảm bảo trạng thái và nghiệp vụ nằm trong commit thích hợp hoặc chỉ phát sự kiện sau commit; với độ bền cao cân nhắc outbox.

**Câu 7.** Hai lần POST có cùng idempotency key và cùng payload nên tạo mấy job?

**Đáp án:** Theo giao thức idempotent được đề xuất, chỉ một job logic; lần retry trả lại job ID/status cũ. Unique constraint và lưu khóa ở nơi dùng chung giúp bảo đảm điều này khi nhiều replica.

**Câu 8.** Vì sao số lượng “accepted” không phản ánh số lượng “completed successfully”?

**Đáp án:** Một task có thể vẫn chờ queue, đang chạy, thất bại, bị hủy hoặc bị mất khi crash. Đếm thành công phải dựa trên terminal state có bằng chứng nghiệp vụ, không phải số lần submit.

## Tóm tắt

**Nhận việc (accepted) là lời hứa về bước tiếp nhận theo hợp đồng; hoàn thành nghiệp vụ (business completed) là kết quả phải có chứng cứ riêng.** `execute`, `submit`, `@Async` và HTTP 202 đều không tự biến một yêu cầu thành nghiệp vụ đã thành công.

Thiết kế tốt phải nối được **request ID → accepted/queued → running → kết quả cuối**, xử lý đúng những lần retry và cửa sổ lỗi, rồi chỉ công bố `SUCCEEDED` khi điều kiện nghiệp vụ thật sự được thỏa. Đó là cách tránh thông báo thành công quá sớm và tránh mất hoặc nhân đôi công việc bất đồng bộ.

## Tài liệu tham khảo

- Java SE 17 — `ExecutorService`, `Future` và memory consistency effects: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Java SE 17 — `CompletableFuture`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Spring Framework Reference — Task Execution and Scheduling, `@Async`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework Javadoc — `ThreadPoolTaskExecutor` và `TaskRejectedException`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- HTTP Semantics (RFC 9110) — 202 Accepted: https://httpwg.org/specs/rfc9110.html#status.202
