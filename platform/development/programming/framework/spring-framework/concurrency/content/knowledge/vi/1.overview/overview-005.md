# Tách thời điểm nhận yêu cầu khỏi thời điểm hoàn thành công việc

> **Module:** Spring Framework - concurrency · **Nhóm kiến thức:** Tổng quan  
> **Trọng tâm:** Hiểu sự khác nhau giữa thời điểm hệ thống tiếp nhận một yêu cầu, thời điểm bắt đầu xử lý và thời điểm công việc thực sự hoàn tất; chọn đúng cách tổ chức tác vụ bất đồng bộ trong ứng dụng Spring.

## 1. Vấn đề và mô hình tư duy

Một yêu cầu HTTP có thể đến trong vài mili giây nhưng công việc phía sau lại mất vài giây hoặc vài phút: tạo báo cáo, xuất tệp, gửi email, lập chỉ mục, xử lý ảnh hoặc đẩy dữ liệu sang dịch vụ khác. Nếu controller làm toàn bộ công việc rồi mới trả lời, thời gian phản hồi HTTP gắn chặt với thời gian xử lý nghiệp vụ.

Có **ba mốc thời gian** cần phân biệt:

1. **Tiếp nhận (accept):** xác thực, phân quyền, kiểm tra dữ liệu, quyết định có nhận việc hay không, tạo mã theo dõi hoặc ghi nhận yêu cầu.
2. **Thực thi (execute):** công việc được lấy khỏi hàng đợi hoặc được giao cho worker để chạy; có thể bắt đầu ngay, bắt đầu muộn hoặc bị từ chối khi hệ thống quá tải.
3. **Hoàn thành (complete):** có kết quả thành công/thất bại cuối cùng; trạng thái này có thể đến rất lâu sau khi client đã nhận phản hồi tiếp nhận.

Ví dụ thời gian:

```text
t0   Client gửi POST /jobs
t1   Server kiểm tra, ghi nhận job J42
t2   Server trả HTTP 202 + địa chỉ GET /jobs/J42
t3   Worker bắt đầu xử lý J42
t4   Worker hoàn tất, lưu SUCCEEDED (hoặc FAILED)
t5   Client tra cứu GET /jobs/J42 để lấy trạng thái
```

Thời điểm `t2` **không cần chờ** `t4`. Đây là ý nghĩa chính của việc tách thời điểm nhận yêu cầu khỏi thời điểm hoàn thành công việc. Tách thời điểm **không đồng nghĩa** tự động có hệ thống chạy song song vô hạn, không chặn luồng hoặc có khả năng chịu lỗi; từng thuộc tính phải được thiết kế riêng.

### Vì sao cần tách?

- **Độ trễ phản hồi:** người dùng có thể nhận ngay mã công việc và tiếp tục thao tác.
- **Sức chứa hệ thống:** thread xử lý HTTP không phải đứng chờ toàn bộ tác vụ dài; các worker có giới hạn tài nguyên riêng.
- **Điều tiết tải:** hàng đợi, giới hạn số việc đang chạy và chính sách từ chối giúp tránh quá tải dây chuyền.
- **Quan sát và phục hồi:** trạng thái công việc, lỗi và lần thử lại được theo dõi tách khỏi vòng đời kết nối HTTP.

Không phải yêu cầu nào cũng nên tách. Nếu client cần kết quả ngay để đưa ra quyết định tiếp theo, công việc rất ngắn hoặc cần trả một lỗi nghiệp vụ trực tiếp trước khi kết thúc HTTP, xử lý đồng bộ có thể đơn giản và phù hợp hơn.

## 2. Phân biệt các cơ chế dễ nhầm trong Spring

| Cơ chế | HTTP trả lúc nào? | Thread HTTP ban đầu | Công việc có sống sau khi HTTP trả? | Phù hợp |
| --- | --- | --- | --- | --- |
| Controller đồng bộ | Sau khi hoàn tất xử lý | Thường bị giữ suốt quá trình | Không phải mô hình tách | Tác vụ nhanh, cần kết quả ngay |
| Spring MVC `Callable`, `WebAsyncTask`, `DeferredResult` | Khi kết quả bất đồng bộ sẵn sàng hoặc hết thời gian chờ | Được giải phóng trong lúc chờ; response vẫn mở | Thông thường **không** tách vòng đời kết quả khỏi HTTP | Tối ưu chờ trong một HTTP response |
| `@Async` + trả `202 Accepted` | Ngay sau khi chấp nhận/giao việc thành công | Trả sớm; việc chạy ở executor | Có thể, trong cùng tiến trình JVM | Tác vụ nền đơn giản, chấp nhận mất việc nếu tiến trình chết |
| Ghi job bền vững + broker/queue + worker | Sau khi job được ghi nhận an toàn | Trả sớm | Có, nếu thiết kế lưu trữ/retry đúng | Việc quan trọng, dài, cần chịu lỗi và mở rộng |

**Hai kiểu “async” không thể hoán đổi:**

- **Async HTTP response:** `Callable` hoặc `DeferredResult` giúp Spring MVC thoát khỏi luồng Servlet ban đầu, sau đó tiếp tục xử lý để trả **cùng một** HTTP response. Kết nối phía client vẫn đợi kết quả.
- **Async business job:** controller trả `202` và mã job; worker hoàn tất sau. Kết quả có thể được lấy bằng polling, thông báo hoặc webhook. Đây mới là cách tách thời điểm phản hồi với thời điểm hoàn thành nghiệp vụ.

`CompletableFuture`, `@Async`, WebFlux hay `Mono` chỉ là công cụ lập trình bất đồng bộ. Việc trả một future hoặc dùng non-blocking I/O không tự động tạo ra một job bền vững, có cơ chế retry và có API theo dõi trạng thái.

## 3. Thiết kế hợp đồng HTTP cho công việc chạy sau

Một hợp đồng phổ biến:

```http
POST /jobs
HTTP/1.1 202 Accepted
Location: /jobs/7c5c...

{
  "jobId": "7c5c...",
  "statusUrl": "/jobs/7c5c..."
}
```

```http
GET /jobs/7c5c...
HTTP/1.1 200 OK

{
  "jobId": "7c5c...",
  "status": "RUNNING"
}
```

Các mã/ý nghĩa cần rõ ràng:

- `202 Accepted`: hệ thống **đã nhận yêu cầu để xử lý**, không khẳng định xử lý thành công; tác vụ vẫn có thể thất bại hoặc không được thực thi.
- `200 OK` từ endpoint tra cứu: việc **tra cứu trạng thái** thành công; trường `status` mới cho biết job đang chạy hay hoàn tất.
- `400`/`422` (tùy hợp đồng): dữ liệu không hợp lệ, không thể nhận việc. `401`/`403`: chưa xác thực hoặc không có quyền.
- `429 Too Many Requests` hoặc `503 Service Unavailable`: quá tải/tạm không nhận thêm việc, kèm chính sách thử lại nếu có.
- `404 Not Found`: không tìm thấy mã job hoặc mã không thuộc quyền truy cập; không suy diễn rằng job đã thất bại.

Trạng thái tối thiểu:

```text
QUEUED ---> RUNNING ---> SUCCEEDED
                 |
                 +------> FAILED
```

Trong hệ thống thực, có thể bổ sung `CANCELLED`, `RETRY_WAIT`, `EXPIRED`, số lần thử, lý do lỗi, `createdAt`, `startedAt`, `finishedAt` và đường dẫn kết quả. Hãy định nghĩa rõ trạng thái cuối và thời gian lưu trữ của job.

**Nguyên tắc:** trước khi phát `202`, phải biết chắc hệ thống đã *chấp nhận* việc theo mức bảo đảm của mình. Nếu thao tác đưa việc vào executor/queue bị từ chối, hãy trả lỗi phù hợp. Nếu công việc quan trọng phải không mất khi ứng dụng khởi động lại, việc “chấp nhận” phải bao gồm một bản ghi/điệp tin bền vững, chứ không chỉ tạo một đối tượng trong RAM.

## 4. Ví dụ chạy được: Spring Boot MVC + `@Async` + tra cứu trạng thái

Ví dụ sau dùng **Java 17+, Spring Boot 3.5.7 (Spring Framework 6.x)** và Maven. Nó cho thấy controller trả `202` nhanh trong khi worker chờ 3 giây để mô phỏng xử lý. Để dễ quan sát, trạng thái chỉ lưu trong `ConcurrentHashMap` **trong bộ nhớ**; đây là bản demo, không phải triển khai chịu lỗi production.

Cấu trúc dự án:

```text
async-jobs-demo/
├── pom.xml
└── src/main/java/com/example/asyncjobs/
    ├── JobDemoApplication.java
    ├── JobStore.java
    ├── JobWorker.java
    └── JobController.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>async-jobs-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/com/example/asyncjobs/JobDemoApplication.java`**

```java
package com.example.asyncjobs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class JobDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JobDemoApplication.class, args);
    }

    @Bean("jobExecutor")
    public ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("job-");
        return executor;
    }
}
```

`@EnableAsync` kích hoạt cơ chế xử lý `@Async`. Bean `jobExecutor` là nhóm luồng **có giới hạn**: tối đa 4 worker và một hàng chờ giới hạn 16 phần tử. Khi hàng chờ đầy và đạt giới hạn luồng, executor từ chối tác vụ; ví dụ xử lý tình huống đó ở controller. Đây là executor chạy **bên trong JVM**.

**`src/main/java/com/example/asyncjobs/JobStore.java`**

```java
package com.example.asyncjobs;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class JobStore {
    private final ConcurrentHashMap<UUID, String> states = new ConcurrentHashMap<>();

    public void create(UUID id) {
        states.put(id, "QUEUED");
    }

    public void update(UUID id, String state) {
        states.put(id, state);
    }

    public String find(UUID id) {
        return states.get(id);
    }

    public void remove(UUID id) {
        states.remove(id);
    }
}
```

`ConcurrentHashMap` cho phép luồng request và worker truy cập an toàn tới từng thao tác trên map. Nó **không** làm job bền vững sau restart và không thay thế cơ sở dữ liệu.

**`src/main/java/com/example/asyncjobs/JobWorker.java`**

```java
package com.example.asyncjobs;

import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class JobWorker {
    private final JobStore store;

    public JobWorker(JobStore store) {
        this.store = store;
    }

    @Async("jobExecutor")
    public void start(UUID id) {
        store.update(id, "RUNNING");
        try {
            // Mô phỏng xử lý mất 3 giây; chỉ worker bị chờ.
            TimeUnit.SECONDS.sleep(3);
            store.update(id, "SUCCEEDED");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            store.update(id, "FAILED");
        } catch (RuntimeException ex) {
            // Trong thực tế cần ghi log, mã lỗi và thông tin chẩn đoán.
            store.update(id, "FAILED");
        }
    }
}
```

Lệnh gọi `worker.start(id)` đi qua **Spring proxy** nên phương thức chạy trên thread của `jobExecutor`. `TimeUnit.SECONDS.sleep(3)` chỉ dùng minh họa tác vụ dài và **không** chạy trên thread HTTP. Trường hợp thất bại cập nhật `FAILED`; với phương thức `@Async void`, exception không tự quay về HTTP response đã gửi.

**`src/main/java/com/example/asyncjobs/JobController.java`**

```java
package com.example.asyncjobs;

import java.net.URI;
import java.util.Map;
import java.util.UUID;

import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/jobs")
public class JobController {
    private final JobStore store;
    private final JobWorker worker;

    public JobController(JobStore store, JobWorker worker) {
        this.store = store;
        this.worker = worker;
    }

    @PostMapping
    public ResponseEntity<Map<String, String>> submit() {
        UUID id = UUID.randomUUID();
        store.create(id);

        try {
            worker.start(id); // Giao việc cho executor qua Spring proxy.
        } catch (TaskRejectedException ex) {
            store.remove(id);
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(Map.of("error", "Executor is full"));
        }

        String path = "/jobs/" + id;
        return ResponseEntity.accepted()
                .location(URI.create(path))
                .body(Map.of("jobId", id.toString(), "statusUrl", path));
    }

    @GetMapping("/{id}")
    public ResponseEntity<Map<String, String>> status(@PathVariable UUID id) {
        String state = store.find(id);
        if (state == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(Map.of(
                "jobId", id.toString(),
                "status", state
        ));
    }
}
```

Controller **không gọi** `get()`, `join()` hoặc đợi kết quả của worker. Sau khi executor nhận tác vụ, controller trả HTTP `202 Accepted` kèm `Location` để client tra cứu. Nếu executor hết chỗ, controller trả `503`, tránh thông báo nhận việc khi chưa thể giao việc. Trong hệ thống thật, phải xác thực, phân quyền và kiểm tra input trước khi chấp nhận; ở đây cố ý không có payload để tập trung vào mốc thời gian.

Chạy dự án (cài JDK 17+ và Maven):

```bash
mvn spring-boot:run

# Ở terminal khác:
curl -i -X POST http://localhost:8080/jobs
# Sao chép jobId từ response:
curl -i http://localhost:8080/jobs/<jobId>
```

Kết quả **minh họa** (UUID thay đổi theo mỗi lần gọi):

```http
HTTP/1.1 202
Location: /jobs/<jobId>

{"jobId":"<jobId>","statusUrl":"/jobs/<jobId>"}
```

Ngay sau POST, GET có thể thấy `QUEUED` hoặc `RUNNING`; khoảng 3 giây sau khi worker bắt đầu sẽ thường thấy `SUCCEEDED`. Nếu worker được lập lịch/chạy nhanh, trạng thái có thể thay đổi trước khi client GET lần đầu; **không** dựa vào thứ tự timing giả định. Không có stdout cố định vì thời điểm xử lý và UUID phụ thuộc lần chạy.

**Các điểm cần quan sát:** POST có thể hoàn tất trước 3 giây; endpoint GET trả trạng thái tại thời điểm được hỏi; thread `job-*` xử lý công việc thay cho thread HTTP; công việc có thể mất nếu JVM dừng.

## 5. Trường hợp chỉ muốn giải phóng thread HTTP, vẫn trả kết quả trong cùng response

Spring MVC có cơ chế async Servlet cho tình huống **client vẫn cần dữ liệu ở chính HTTP response đang mở**. Ví dụ phương thức bổ sung trong một `@RestController`:

```java
@GetMapping("/preview")
public java.util.concurrent.Callable<String> preview() {
    return () -> {
        java.util.concurrent.TimeUnit.SECONDS.sleep(2);
        return "PREVIEW_READY";
    };
}
```

Đây là **đoạn phương thức minh họa** cần đặt trong controller có `@GetMapping` hoạt động; nó không phải chương trình Java độc lập. Spring MVC nhận `Callable`, bắt đầu xử lý Servlet async, giải phóng thread Servlet ban đầu rồi chạy callable trên `AsyncTaskExecutor`. Sau khi callable hoàn tất, Spring dispatch lại để trả body `PREVIEW_READY`. Client vẫn phải đợi khoảng 2 giây để nhận response này.

`DeferredResult<T>` dùng khi kết quả được cung cấp bởi **một sự kiện bên ngoài** hoặc callback thay vì chạy trực tiếp một `Callable`. Ứng dụng giữ đối tượng `DeferredResult` và một luồng khác gọi `setResult` hoặc `setErrorResult`. Cần xử lý timeout và completion để không giữ yêu cầu treo mãi. `WebAsyncTask` cung cấp cách đặt timeout/executor riêng cho `Callable`.

Không nên dùng `Callable`/`DeferredResult` rồi kết luận “đã trả việc về nền”: kết nối HTTP vẫn gắn với việc chờ kết quả. Ngược lại, một endpoint `202` không cần giữ response mở nhưng phải cung cấp cách quan sát kết quả về sau.

## 6. Thiết kế production: nhận việc chắc chắn, thực thi có kiểm soát

Ví dụ trên dạy **cơ chế**, chưa bảo đảm độ bền. Với báo cáo lớn, gửi email quan trọng hoặc tác vụ có thể chạy hàng phút, hãy tách thành các thành phần:

```text
Client
  |
  | POST /jobs (+ Idempotency-Key nếu cần)
  v
HTTP API --validate/auth--> DB: INSERT job(status=QUEUED)
  |                                |
  | HTTP 202 + jobId               | Worker/broker nhận nhiệm vụ
  v                                v
Client --GET /jobs/{id}--> DB <-- Worker cập nhật RUNNING/SUCCEEDED/FAILED
```

Có hai triển khai phổ biến:

1. **DB làm job queue:** giao dịch lưu job `QUEUED`, worker truy vấn/claim job có khóa hoặc lease, cập nhật trạng thái. Cần xử lý claim hết hạn, phân chia job giữa nhiều instance, retry và crash.
2. **DB + message broker:** API ghi nhận ý định làm việc và phát message sang RabbitMQ/Kafka hoặc hệ tương đương; worker tiêu thụ. Nếu phải bảo đảm không mất job giữa thao tác commit DB và publish message, dùng **transactional outbox** (ghi job + outbox trong cùng giao dịch, publisher phát message sau commit). Consumer phải xử lý khả năng message được nhận lặp.

Các quyết định tối thiểu cần xác định:

- **Ranh giới chấp nhận:** xác thực, quyền truy cập, input hợp lệ, quota, ghi job/queue thành công rồi mới trả `202`. Nếu ghi thất bại, trả lỗi thay vì tạo mã job “ảo”.
- **Backpressure:** executor/queue có giới hạn; từ chối hoặc trì hoãn nhận job khi quá tải, không tạo thread không giới hạn. Tách metric **HTTP latency** với **queue wait time** và **job execution time**.
- **Idempotency:** client có thể gửi lại POST do timeout; nếu nghiệp vụ không được chạy hai lần, hỗ trợ idempotency key và ánh xạ khóa đó tới một job. Worker cũng cần idempotent khi retry/redelivery.
- **Retry và lỗi:** phân biệt lỗi tạm thời với lỗi vĩnh viễn, dùng backoff, giới hạn lần thử, lưu nguyên nhân và đưa trường hợp hết lượt retry vào `FAILED`/dead-letter theo hợp đồng.
- **Kết quả và quyền:** lưu output hoặc URL tải kết quả khi hoàn tất; kiểm tra quyền sở hữu job trên mọi lần GET/cancel/download, không để ai biết UUID cũng xem được dữ liệu.
- **Timeout và hủy:** timeout của HTTP không tự hủy job; cancellation cần trạng thái, tín hiệu worker và chính sách dọn tài nguyên riêng.
- **Quan sát:** có correlation/job ID trong log và trace, đo số job đang chờ, tuổi job lâu nhất, số worker đang chạy, tỷ lệ thất bại/thử lại, thời gian từ nhận đến hoàn tất.
- **Khả năng khôi phục:** sau restart phải nhận ra job `RUNNING` bị bỏ dở, có lease/heartbeat và cơ chế chạy lại hợp lệ; không dựa vào RAM.

**Lưu ý về giao dịch và context:** `@Async` đổi thread. Transaction của request không tự lan sang thread worker; `SecurityContext`, request attributes và MDC dựa trên `ThreadLocal` cũng không mặc nhiên đi theo. Worker nên nhận các dữ liệu cần thiết dưới dạng giá trị/ID tường minh và tự mở transaction khi cần. Nếu yêu cầu “chỉ bắt đầu sau DB commit”, dùng điểm kích hoạt sau commit thích hợp; nếu cần *bền vững* qua crash, dùng outbox/queue thay vì chỉ `@TransactionalEventListener` + `@Async`.

## 7. Lỗi thường gặp và cách tự kiểm tra

| Hiểu sai/cách làm sai | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Trả `200 OK` hoặc “completed” khi vừa giao việc | Client tưởng nghiệp vụ đã thành công | Trả `202`, mã job và endpoint trạng thái |
| Gọi `future.get()`, `join()` hoặc chờ worker trong controller | HTTP vẫn đợi công việc dài | Chỉ giao việc rồi trả; đọc trạng thái ở lần gọi riêng |
| Gọi phương thức `@Async` bằng `this.start()` trong cùng bean | Self-invocation bỏ qua proxy, công việc có thể chạy đồng bộ | Gọi thông qua Spring bean khác hoặc cơ chế scheduling rõ ràng |
| Cho rằng `@Async` tự có hàng đợi bền vững | Restart/crash làm mất việc, mất trạng thái RAM | DB/broker, retry, recovery |
| Dùng thread pool/queue không giới hạn hoặc `CallerRunsPolicy` không cân nhắc | Hết tài nguyên; `CallerRunsPolicy` có thể chạy job ngay trên thread HTTP | Đặt giới hạn, quan sát độ sâu queue, từ chối có chủ đích |
| Không xử lý exception trong tác vụ `@Async void` | HTTP đã trả; lỗi không được gửi về client | Bắt lỗi, cập nhật trạng thái, log và alert |
| Dùng `DeferredResult` mà quên timeout/cleanup | HTTP request treo, giữ tài nguyên | Timeout callback, error result, dọn listener |
| Dựa vào transaction/context của thread gọi | Đọc dữ liệu chưa commit, thiếu principal/trace | Truyền ID rõ ràng, transaction/context riêng |
| Retry vô điều kiện với thao tác tạo side effect | Gửi email/thu tiền/ghi dữ liệu hai lần | Idempotency, dedupe và chính sách retry |

**Câu hỏi tự kiểm tra:**

1. Nếu POST trả sau 20 ms nhưng worker mất 15 giây, HTTP status nào hợp lý và client biết kết quả qua đâu?
2. `Callable` trong Spring MVC giải phóng thread HTTP ban đầu; tại sao client vẫn phải chờ response?
3. Điều gì xảy ra với job lưu trong `ConcurrentHashMap` và executor khi tiến trình JVM tắt?
4. Tại sao việc gọi `@Async` trong cùng bean có thể chạy đồng bộ?
5. Khi queue đầy hoặc broker không nhận message, API có nên tiếp tục trả `202` không?

Đáp án định hướng: (1) `202` + job ID/status endpoint; (2) response HTTP vẫn mở đến lúc có kết quả; (3) job/trạng thái RAM không bền vững; (4) không đi qua Spring proxy; (5) không, trừ khi đã có một bản ghi bền vững bảo đảm job được xử lý sau.

## 8. Ghi nhớ

**Tách tiếp nhận khỏi hoàn thành** là quyết định về **vòng đời nghiệp vụ và hợp đồng với client**. Spring hỗ trợ nhiều cơ chế chạy bất đồng bộ, nhưng cần chọn đúng theo điều người dùng chờ đợi:

- Cần **kết quả trong cùng HTTP response**: cân nhắc Spring MVC `Callable`/`DeferredResult` với timeout và executor phù hợp.
- Cần **nhận việc nhanh, biết kết quả sau**: dùng `202 Accepted`, job ID và cơ chế tra cứu; `@Async` đủ cho demo/tác vụ nền chấp nhận rủi ro trong JVM.
- Cần **không mất việc, retry và mở rộng nhiều instance**: lưu job bền vững, queue/outbox/worker, idempotency và quan sát vận hành.

**Tài liệu chính thức:** [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) · [Spring Framework – Asynchronous Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html) · [HTTP Semantics RFC 9110, §15.3.3 – 202 Accepted](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.3)