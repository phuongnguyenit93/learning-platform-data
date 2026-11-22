# Ví dụ xuyên suốt: xử lý báo cáo và cập nhật dữ liệu định kỳ

## 1. Bài toán và mục tiêu

Giả sử một dịch vụ Spring nhận yêu cầu tạo báo cáo doanh thu/tổng hợp qua HTTP. Việc tổng hợp có thể mất vài giây hoặc vài phút; đồng thời ứng dụng phải cập nhật số liệu nền theo chu kỳ. Nếu xử lý báo cáo ngay trên luồng HTTP, người dùng phải giữ kết nối lâu và số luồng phục vụ request có thể bị chiếm hết. Nếu tự tạo luồng mới cho mỗi request, số luồng và bộ nhớ dễ tăng ngoài kiểm soát.

Ta tách hai loại công việc:

1. **Báo cáo theo yêu cầu:** `POST /reports` tạo một mã công việc, trả `202 Accepted` sớm; một `TaskExecutor` có giới hạn luồng xử lý ở nền. `GET /reports/{id}` trả trạng thái `PENDING`, `RUNNING`, `DONE` hoặc `FAILED`.
2. **Cập nhật dữ liệu định kỳ:** `TaskScheduler` kích hoạt một phương thức `@Scheduled`, cập nhật bảng số liệu mỗi 30 giây sau khi lần trước kết thúc. API `GET /metrics` cho phép quan sát giá trị hiện tại.

Trong bản demo, dữ liệu là một bộ đếm trong H2 và báo cáo đọc bộ đếm rồi giả lập bước tổng hợp lâu. Đây là mô hình tối giản để thấy luồng thực thi và thời điểm đọc dữ liệu; thực tế có thể thay SQL bằng truy vấn tổng hợp, xuất CSV/PDF, đọc nguồn ngoài hoặc lưu kết quả lên object storage.

~~~mermaid
flowchart LR
    U[Client] -->|POST /reports| C[ReportController]
    C -->|lưu PENDING| R[ReportStore]
    C -->|gọi bean khác| E[reportExecutor]
    E --> W[ReportWorker]
    W -->|đọc số liệu| DB[(H2 metrics)]
    W -->|RUNNING / DONE / FAILED| R
    U -->|GET /reports/id| C
    S[taskScheduler] -->|mỗi 30s sau khi hoàn tất| J[MetricJob]
    J -->|UPDATE atomic| DB
    U -->|GET /metrics| DB
~~~

**Hai khái niệm khác nhau:** `TaskExecutor` quyết định *ở đâu và với bao nhiêu luồng* một tác vụ được chạy; `TaskScheduler` quyết định *khi nào* tác vụ được kích hoạt. `@Async` thường gửi công việc đến executor; `@Scheduled` đăng ký lịch với scheduler. Không có cơ chế nào trong hai cơ chế này tự bảo đảm lưu bền vững công việc khi tiến trình bị tắt.

## 2. Tạo ứng dụng chạy được (Java 17, Spring Boot 3.3.5)

Dùng Spring Boot để khởi tạo ứng dụng, web server và kết nối H2; các annotation và executor/scheduler được minh họa là chức năng của **Spring Framework**. Cấu trúc:

~~~text
spring-concurrency-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/demo/
    │   ├── DemoApplication.java
    │   ├── ReportStatus.java
    │   ├── ReportStore.java
    │   ├── ReportWorker.java
    │   ├── ReportController.java
    │   ├── MetricJob.java
    │   └── MetricsController.java
    └── resources/
        ├── schema.sql
        └── data.sql
~~~

### 2.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>spring-concurrency-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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
~~~

### 2.2. Bật scheduling/async và cấu hình hai pool

`src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("report-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }

    @Bean
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("schedule-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(20);
        return scheduler;
    }
}
~~~

`reportExecutor` có 2 luồng lõi, tối đa 4 luồng, hàng đợi tối đa 20 công việc; khi đầy có thể từ chối yêu cầu mới. Với cấu hình `ThreadPoolExecutor` thông thường, các luồng vượt số lõi chỉ được tạo khi hàng đợi đã đầy, vì thế `maxPoolSize` không có nghĩa lúc nào cũng có 4 luồng. `taskScheduler` là pool riêng cho tác vụ định kỳ, tránh để việc tạo báo cáo chiếm luồng đặt lịch. Tên bean `taskScheduler` cho phép cơ chế `@Scheduled` tìm scheduler này.

### 2.3. Khởi tạo dữ liệu

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY,
    total BIGINT NOT NULL
);
~~~

`src/main/resources/data.sql`:

~~~sql
INSERT INTO metrics (id, total) VALUES (1, 0);
~~~

Spring Boot tự khởi tạo các script SQL này khi dùng H2 nhúng theo cấu hình mặc định. Mỗi lần khởi động mới với H2 in-memory, dữ liệu demo có thể bắt đầu lại từ 0. Cập nhật `total = total + 1` thực hiện ngay trong SQL, tránh kiểu đọc số cũ rồi ghi lại dễ mất cập nhật khi có nhiều luồng.

### 2.4. Kho trạng thái báo cáo

`src/main/java/com/example/demo/ReportStatus.java`:

~~~java
package com.example.demo;

import java.util.UUID;

public record ReportStatus(UUID id, String status, Long total, String error) {
}
~~~

`src/main/java/com/example/demo/ReportStore.java`:

~~~java
package com.example.demo;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Service;

@Service
public class ReportStore {
    private final ConcurrentMap<UUID, ReportStatus> jobs = new ConcurrentHashMap<>();

    public void pending(UUID id) {
        jobs.put(id, new ReportStatus(id, "PENDING", null, null));
    }

    public void running(UUID id) {
        jobs.put(id, new ReportStatus(id, "RUNNING", null, null));
    }

    public void done(UUID id, long total) {
        jobs.put(id, new ReportStatus(id, "DONE", total, null));
    }

    public void failed(UUID id, String error) {
        jobs.put(id, new ReportStatus(id, "FAILED", null, error));
    }

    public ReportStatus find(UUID id) {
        return jobs.get(id);
    }
}
~~~

`ConcurrentHashMap` cho phép các luồng HTTP và luồng worker truy cập đồng thời; mỗi `ReportStatus` là record bất biến nên các lần cập nhật thay thế nguyên giá trị. Đây chỉ là trạng thái trong RAM: restart sẽ mất công việc và trạng thái; hệ thống thật nên lưu ở bảng `report_jobs` hoặc kho lưu bền vững, có chính sách giữ/xóa trạng thái.

### 2.5. Worker chạy bất đồng bộ

`src/main/java/com/example/demo/ReportWorker.java`:

~~~java
package com.example.demo;

import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {
    private final JdbcTemplate jdbc;
    private final ReportStore store;

    public ReportWorker(JdbcTemplate jdbc, ReportStore store) {
        this.jdbc = jdbc;
        this.store = store;
    }

    @Async("reportExecutor")
    public void generate(UUID id) {
        store.running(id);
        try {
            Long total = jdbc.queryForObject(
                    "SELECT total FROM metrics WHERE id = 1", Long.class);
            if (total == null) {
                throw new IllegalStateException("Không tìm thấy dữ liệu");
            }

            // Chỉ giả lập bước tổng hợp/tạo file mất thời gian.
            Thread.sleep(1500);
            store.done(id, total);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            store.failed(id, "Công việc bị ngắt khi dừng ứng dụng");
        } catch (Exception ex) {
            store.failed(id, "Không thể tạo báo cáo");
        }
    }
}
~~~

`@Async("reportExecutor")` chỉ có hiệu lực khi gọi phương thức qua Spring proxy, trong ví dụ là **ReportController gọi bean ReportWorker khác**. Nếu gọi `this.generate(id)` từ một phương thức cùng class, lời gọi nội bộ sẽ bỏ qua proxy và thường chạy đồng bộ. Không truyền `HttpServletRequest`, `EntityManager` hay tài nguyên request đang đóng sang luồng nền; chuyển ID/dữ liệu đầu vào cần thiết rồi mở tài nguyên ở worker. `Thread.sleep` chỉ là mô phỏng, không phải kỹ thuật xử lý báo cáo.

Nếu muốn lấy kết quả qua API Java (thay vì tra trạng thái bằng HTTP), phương thức `@Async` có thể trả `CompletableFuture<T>`. Không gọi `join()` hay `get()` ngay trên luồng HTTP nếu mục tiêu là trả phản hồi nhanh.

### 2.6. HTTP API trả về mã công việc

`src/main/java/com/example/demo/ReportController.java`:

~~~java
package com.example.demo;

import java.net.URI;
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
@RequestMapping("/reports")
public class ReportController {
    private final ReportStore store;
    private final ReportWorker worker;

    public ReportController(ReportStore store, ReportWorker worker) {
        this.store = store;
        this.worker = worker;
    }

    @PostMapping
    public ResponseEntity<ReportStatus> submit() {
        UUID id = UUID.randomUUID();
        store.pending(id);
        try {
            worker.generate(id);
        } catch (TaskRejectedException ex) {
            store.failed(id, "Hàng đợi đang đầy, hãy thử lại");
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(store.find(id));
        }
        return ResponseEntity.accepted()
                .location(URI.create("/reports/" + id))
                .body(store.find(id));
    }

    @GetMapping("/{id}")
    public ResponseEntity<ReportStatus> status(@PathVariable UUID id) {
        ReportStatus result = store.find(id);
        return result == null
                ? ResponseEntity.notFound().build()
                : ResponseEntity.ok(result);
    }
}
~~~

`202 Accepted` xác nhận yêu cầu đã được nhận để xử lý, chưa cam kết báo cáo thành công. Header `Location` trỏ đến tài nguyên trạng thái. Tại thời điểm phản hồi, `status` có thể đã là `PENDING` hoặc `RUNNING`, thậm chí `DONE` nếu công việc hoàn thành rất nhanh: không được viết test giả định chính xác một trạng thái tức thời. Nếu executor từ chối nhận vì đầy, API trả `503 Service Unavailable`.

### 2.7. Cập nhật định kỳ và API xem số liệu

`src/main/java/com/example/demo/MetricJob.java`:

~~~java
package com.example.demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MetricJob {
    private final JdbcTemplate jdbc;

    public MetricJob(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Scheduled(initialDelay = 5_000, fixedDelay = 30_000)
    public void refresh() {
        int rows = jdbc.update(
                "UPDATE metrics SET total = total + 1 WHERE id = 1");
        if (rows != 1) {
            throw new IllegalStateException("Thiếu dòng metrics id=1");
        }
    }
}
~~~

`src/main/java/com/example/demo/MetricsController.java`:

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MetricsController {
    private final JdbcTemplate jdbc;

    public MetricsController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @GetMapping("/metrics")
    public Map<String, Long> current() {
        Long total = jdbc.queryForObject(
                "SELECT total FROM metrics WHERE id = 1", Long.class);
        return Map.of("total", total);
    }
}
~~~

Sau khi ứng dụng chạy khoảng 5 giây, `MetricJob` bắt đầu lần đầu. Với `fixedDelay = 30_000`, lần tiếp theo bắt đầu ít nhất 30 giây *sau khi lần trước kết thúc* (có thể trễ vì hệ thống bận). Bộ đếm tăng 1 mỗi lượt thành công; nếu một báo cáo đọc trước lúc cập nhật, nó có thể phản ánh giá trị cũ. Đó là ảnh chụp dữ liệu tại thời điểm đọc, không phải lỗi đồng bộ.

## 3. Chạy thử luồng xử lý

Cần JDK 17+ và Maven. Tại thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Trong terminal khác:

~~~bash
curl -s http://localhost:8080/metrics
curl -i -X POST http://localhost:8080/reports
# Lấy id trong JSON phản hồi POST, rồi thay UUID_THUC bằng giá trị đó:
curl -s http://localhost:8080/reports/UUID_THUC
~~~

Ví dụ `GET /metrics` lúc mới chạy trả `{"total":0}`. Sau lần cập nhật đầu, số này trở thành 1, sau đó tăng tiếp khi các lượt chạy thành công. `POST /reports` trả HTTP 202 và một JSON dạng:

~~~json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PENDING",
  "total": null,
  "error": null
}
~~~

UUID trên **chỉ minh họa**; trạng thái ban đầu có thể khác do xử lý song song. Dùng UUID thực tế do POST trả về để gọi GET. Sau khoảng 1,5 giây tính từ khi worker bắt đầu, phản hồi có dạng:

~~~json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "DONE",
  "total": 1,
  "error": null
}
~~~

Giá trị `total` phụ thuộc thời điểm worker đọc bảng, không cố định là 1. Để quan sát giới hạn hàng đợi, gửi đồng thời nhiều POST; khi executor quá tải, một số request có thể nhận 503. Khi ứng dụng bị tắt/khởi động lại, H2 in-memory và `ReportStore` mất dữ liệu demo.

## 4. Tại sao thiết kế này không làm nghẽn HTTP?

- **Luồng request:** tạo UUID và trạng thái `PENDING`, gửi nhiệm vụ vào pool, trả 202 nhanh; không chờ `Thread.sleep`.
- **Luồng report:** đánh dấu `RUNNING`, đọc DB, thực hiện bước chậm, lưu `DONE`/`FAILED`; số tác vụ hoạt động đồng thời bị giới hạn bởi pool.
- **Luồng scheduler:** độc lập với report pool; gọi thao tác cập nhật nhỏ, rồi đăng ký lượt tiếp theo.
- **Trạng thái chia sẻ:** `ConcurrentHashMap` an toàn cho các thao tác `put/get` riêng lẻ; nếu cần nhiều bước cập nhật trạng thái có điều kiện (ví dụ `PENDING -> RUNNING` một lần), phải dùng `compute`/CAS hoặc ràng buộc trạng thái trong DB.

Dù hai pool tách luồng, chúng vẫn dùng chung tài nguyên thật như connection pool, CPU, RAM và DB. Nếu 50 báo cáo đều chạy truy vấn nặng, tác vụ scheduled vẫn có thể chậm vì DB quá tải. Do đó phải đo thời gian, giới hạn truy cập DB và có cơ chế backpressure.

### So sánh cơ chế đặt lịch

| Cách | Ý nghĩa | Phù hợp |
| --- | --- | --- |
| `@Scheduled(fixedDelay = 30000)` | Chờ 30 giây sau khi lần trước *kết thúc* | Đồng bộ dữ liệu/polling không cần nhịp khởi động cố định |
| `@Scheduled(fixedRate = 30000)` | Nhắm thời điểm bắt đầu theo chu kỳ 30 giây | Công việc nhẹ, cần nhịp đều; nếu tác vụ chậm có thể bị trễ |
| `@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")` | Chạy theo lịch, ví dụ 02:00 mỗi ngày theo múi giờ xác định | Báo cáo cuối ngày, đóng sổ |

Đây là **ba lựa chọn thay thế** cho lịch của cùng một job, không đặt cả ba annotation lên phương thức demo. `fixedRate` không tự bảo đảm thực thi song song các lượt của cùng một job; lịch và pool còn ảnh hưởng đến hành vi. Nếu từ một lượt scheduled lại gửi công việc sang executor, các lần xử lý nền có thể chồng nhau, vì thế cần kiểm soát trùng lặp.

## 5. Chuyển demo thành thiết kế dùng trong sản xuất

### 5.1. Lưu bền vững và idempotency

Với báo cáo mất hàng phút, lưu mỗi job trong DB với các trường như `id`, `request_key`, `state`, `created_at`, `attempts`, `result_location`, `error_code`. Khi client gửi lại do timeout, dùng idempotency key hoặc ràng buộc unique để tránh tạo hai báo cáo giống nhau. Worker nên cập nhật có điều kiện, ví dụ chỉ một worker được chuyển `PENDING` sang `RUNNING`; lưu file báo cáo vào nơi dùng chung thay vì RAM của một instance.

Tác vụ định kỳ cần lưu watermark như `last_processed_at` hoặc `source_version`. Mỗi lượt chỉ đọc dữ liệu mới và `UPSERT` theo khóa nghiệp vụ; nếu retry, kết quả không bị cộng/nhân đôi sai. Câu SQL tăng bộ đếm trong demo **không idempotent**: gọi hai lần sẽ tăng hai lần, nên không dùng nguyên mẫu này cho dữ liệu tài chính thực.

### 5.2. Nhiều instance và transaction

`@Scheduled` được đăng ký **trong từng application context**. Nếu chạy 3 pod, mỗi pod có thể chạy job của chính nó: bảng chung có nguy cơ bị cập nhật 3 lần. Để bảo đảm một lượt logic chạy một lần trên toàn cụm, dùng khóa phân tán/DB lock, scheduler bên ngoài hoặc hệ thống hàng đợi có cơ chế nhận việc; thiết kế tiếp nhận retry vì sự cố có thể xảy ra giữa lúc làm việc và lúc ghi nhận hoàn tất.

`@Transactional` gắn với ngữ cảnh của luồng đang thực thi. Transaction của HTTP request **không tự truyền** vào worker `@Async`. Nếu cần giao dịch, mở transaction ở phương thức service được worker gọi trên luồng nền hoặc dùng `TransactionTemplate`; tránh giữ transaction suốt thời gian tạo file hay gọi API ngoài. Với JDBC demo, mỗi câu UPDATE tự commit qua kết nối mặc định khi không có transaction bao quanh.

### 5.3. Lỗi, tài nguyên, dừng ứng dụng

- `@Async void` không có Future trả về cho caller; worker nên bắt/ghi lỗi nghiệp vụ, cập nhật `FAILED`, đồng thời log kèm job ID. Nếu bỏ qua exception, cần cấu hình `AsyncUncaughtExceptionHandler` cho lỗi chưa được bắt.
- Job `@Scheduled` có thể gặp lỗi mỗi lượt. Không chỉ trông chờ log: thêm số lần thất bại, timestamp lần thành công gần nhất, cảnh báo khi quá hạn, timeout khi gọi dịch vụ ngoài và retry với backoff phù hợp.
- Giới hạn `corePoolSize`, `maxPoolSize`, `queueCapacity` theo tải và connection pool; trả 429/503 khi không nhận thêm việc. Hàng đợi trong bộ nhớ không phải message queue bền vững.
- Theo dõi `active threads`, `queued tasks`, `rejected tasks`, thời gian hoàn thành, tỷ lệ lỗi, và độ trễ từ `PENDING` sang `RUNNING`. Dùng correlation/job ID trong log; MDC và Spring Security context không mặc nhiên được mang qua mọi luồng, cần propagation có chủ đích.
- Khi dừng, pool có thể đợi công việc đang chạy trong giới hạn đã cấu hình; giới hạn 20 giây ở demo không bảo đảm báo cáo dài hoàn tất. Với job quan trọng, cần cơ chế ghi nhận checkpoint và khôi phục sau restart.

### 5.4. Các lỗi dễ gặp

| Triệu chứng | Nguyên nhân hay gặp | Hướng xử lý |
| --- | --- | --- |
| `@Async` vẫn chặn HTTP | Gọi nội bộ `this.method()`; thiếu `@EnableAsync` | Gọi qua bean khác/proxy, kiểm tra thread name |
| `@Scheduled` không chạy | Thiếu `@EnableScheduling`; bean chưa được Spring quản lý | Đăng ký bean, kiểm tra logs và startup |
| Báo cáo trùng | Client retry hoặc nhiều worker/pod nhận cùng việc | Idempotency key, trạng thái chuyển có điều kiện |
| Số liệu bị cộng lặp | Nhiều pod cùng chạy lịch hoặc retry không idempotent | Khóa toàn cụm, watermark, upsert |
| Báo cáo thấy dữ liệu cũ | Đọc snapshot trước lần cập nhật mới | Ghi thời điểm snapshot, định nghĩa SLA về độ mới |
| Request hết luồng/DB nghẽn | Pool và hàng đợi không giới hạn hoặc truy vấn nặng | Pool bounded, timeout, backpressure, đo tải |
| Công việc mất sau restart | Trạng thái/queue nằm trong RAM | DB/job broker, cơ chế resume/retry |

## 6. Checklist kiểm thử và câu hỏi tự kiểm tra

1. **Luồng HTTP:** POST trả 202 nhanh hơn bước giả lập 1,5 giây; kiểm tra `Location` và GET bằng ID thực tế; trạng thái cuối là `DONE` hoặc `FAILED`.
2. **Lịch:** GET `/metrics` trước và sau ít nhất một lần chạy scheduled, giá trị tăng; thay `fixedDelay` bằng khoảng ngắn trong test và xác minh thời điểm bắt đầu được tính từ lần trước hoàn tất.
3. **Tải đồng thời:** gửi nhiều POST, đo số luồng `report-*`, độ dài queue, 503 khi bão hòa; bảo đảm scheduler tiếp tục hoạt động.
4. **Lỗi:** tạm làm truy vấn DB thất bại, xác minh job chuyển `FAILED` và có log/metric đủ để điều tra; kiểm thử interrupt/dừng ứng dụng.
5. **Đa instance:** chạy hai instance cùng DB thử nghiệm để quan sát lịch có thể chạy hai lần; sau đó thử cơ chế khóa hoặc dedup tương ứng.
6. **Tính nhất quán:** xác định báo cáo phản ánh số liệu tại thời điểm bắt đầu, thời điểm SELECT hay thời điểm hoàn tất; không hứa giá trị “mới nhất” nếu nghiệp vụ chưa quy định.

**Tự trả lời:** (a) Vì sao `@Async` nên nằm ở bean khác với caller? (b) Khi chạy 3 pod, sẽ có bao nhiêu lần `@Scheduled` có thể được kích hoạt mỗi chu kỳ? (c) Vì sao phải giới hạn hàng đợi? (d) Transaction HTTP có theo sang async worker không? (e) Làm thế nào để retry bản cập nhật định kỳ mà không tính trùng?

Tài liệu chính thức: [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html).