# Ảnh hưởng của luồng ảo đến các thiết lập kích thước nhóm luồng truyền thống trong Spring Boot

## 1. Vấn đề cần hiểu

Khi chuyển một ứng dụng Spring Boot từ **platform threads** (luồng hệ điều hành do JVM quản lý) sang **virtual threads** (luồng ảo của Java 21+), nhiều tham số cấu hình vốn được dùng để điều chỉnh thread pool **không còn kiểm soát số lượng tác vụ đồng thời theo cách cũ**.

Ví dụ trước đây một service có thể sử dụng:

```properties
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=32
spring.task.execution.pool.queue-capacity=100
spring.task.scheduling.pool.size=4
```

Nếu bật:

```properties
spring.threads.virtual.enabled=true
```

trên Java 21+ với **task executor và task scheduler do Spring Boot 3.3 tự cấu hình**, những thuộc tính `pool.*` trên **không còn là núm điều chỉnh thread pool của các bean tự cấu hình**. Nguyên nhân là Boot chọn những implementation khác:

- Task executor mặc định chuyển từ `ThreadPoolTaskExecutor` sang `SimpleAsyncTaskExecutor` sử dụng virtual threads.
- Task scheduler mặc định chuyển từ `ThreadPoolTaskScheduler` sang `SimpleAsyncTaskScheduler` sử dụng virtual threads.
- Virtual threads được JVM lập lịch trên một tập platform threads dùng chung, không dùng một fixed thread pool riêng theo mô hình “32 worker threads + hàng đợi 100 tasks”.
- Giới hạn số task được phép xử lý đồng thời, số connection và năng lực hệ thống bên ngoài **vẫn phải thiết kế**; chỉ thay cách ràng buộc chúng.

**Cảnh báo chính:** không được suy diễn từ dòng `spring.threads.virtual.enabled=true` rằng **mọi thread pool trong JVM hoặc mọi cấu hình `max-size` đều bị vô hiệu**. Chỉ những subsystem **thực sự chuyển sang implementation virtual-thread tương ứng** mới mất ý nghĩa của tham số pool truyền thống. Custom `ThreadPoolExecutor`, JDBC connection pool, Netty event loop, HTTP client pool và các giới hạn tài nguyên khác vẫn có logic độc lập.

Phạm vi bài này là **Spring Boot 3.3.x, Spring Framework 6.1.x và Java 21+**, tập trung vào việc kiểm tra và điều chỉnh **cấu hình kích thước nhóm luồng** khi triển khai virtual threads.

## 2. Hai mô hình thực thi cần phân biệt

### 2.1. Platform thread pool truyền thống

Trong mô hình thread pool, số thread vật lý hoạt động được quản lý bởi một executor:

```text
Submit tasks
     |
     v
ThreadPoolTaskExecutor
     |
     +-- corePoolSize = 8
     +-- maxPoolSize  = 32
     +-- queueCapacity = 100
     |
     +-- Platform worker 1 -> task A
     +-- Platform worker 2 -> task B
     +-- ...
     +-- Platform worker N -> task N
     |
     +-- Waiting queue -> task N+1, ...
```

Một tác vụ I/O blocking có thể giữ một platform thread trong suốt thời gian chờ. Vì vậy doanh nghiệp thường đặt `core-size`, `max-size`, `queue-capacity`, `keep-alive` và rejected-execution policy để quản lý CPU, tài nguyên và khả năng chịu tải.

**Các nút điều chỉnh pool ở đây có ý nghĩa trực tiếp với executor đó.**

### 2.2. Virtual thread-per-task

Với cơ chế virtual thread-per-task:

```text
Submit tasks
     |
     v
SimpleAsyncTaskExecutor (virtualThreads=true)
     |
     +-- Virtual thread A -> task A
     +-- Virtual thread B -> task B
     +-- Virtual thread C -> task C
     +-- ...
     |
     v
JVM virtual-thread scheduler
     |
     +-- Carrier/platform threads dùng chung
     +-- Mount/unmount virtual threads khi thích hợp
```

`SimpleAsyncTaskExecutor` **không duy trì một pool worker cố định** để tái sử dụng giống `ThreadPoolTaskExecutor`. Mỗi lần thực thi có thể được cấp một thread mới; khi dùng virtual threads, chi phí tạo thread thấp hơn nhiều so với việc tạo platform thread trong nhiều tình huống.

Điều đó giải thích vì sao:

- `pool.core-size` không còn mô tả bao nhiêu virtual threads được giữ sẵn.
- `pool.max-size` không còn là trần mặc định của số virtual threads đang thực thi.
- `pool.queue-capacity` không còn là hàng đợi cố định trước dàn worker của `ThreadPoolTaskExecutor`.
- `pool.keep-alive` không còn mô tả thời gian platform worker thread được giữ sống trong executor mặc định.
- Đổi số virtual threads **không tương đương** đổi số carrier threads hay số CPU cores.

**Virtual thread không đồng nghĩa CPU vô hạn.** Công việc CPU-bound vẫn chạy trên CPU hữu hạn. Lợi ích chính là khả năng quản lý nhiều nhiệm vụ **blocking I/O** mà không cần giữ một platform thread riêng cho mỗi nhiệm vụ đang chờ.

## 3. Bật virtual threads bằng cấu hình nào?

Với Spring Boot 3.3 và **JDK 21 hoặc mới hơn**:

```properties
spring.threads.virtual.enabled=true
```

Tương đương trong YAML:

```yaml
spring:
  threads:
    virtual:
      enabled: true
```

Để chạy ứng dụng chủ yếu dựa vào các scheduled background jobs mà không có non-daemon thread giữ JVM sống, có thể thêm:

```properties
spring.main.keep-alive=true
```

Virtual threads là daemon threads; chúng **không tự giữ JVM tồn tại** nếu mọi non-daemon thread khác đã kết thúc. `spring.main.keep-alive=true` là lựa chọn Boot cung cấp cho tình huống ứng dụng cần tiếp tục hoạt động. Đừng thêm nó vô điều kiện vào mọi công cụ CLI ngắn hạn: một batch job có chủ đích chạy xong và thoát thường không muốn chờ vô hạn.

### 3.1. Cấu hình chưa đủ nếu runtime không phù hợp

- Java 17 **không có API virtual threads của Java 21**; ứng dụng phải chạy bằng JDK 21+.
- Kiểm tra cả JDK chạy Gradle/Maven và **runtime JVM thật** của process.
- Đừng kết luận virtual threads đang hoạt động chỉ vì giá trị property tồn tại; xác nhận **loại executor** và `Thread.currentThread().isVirtual()` tại code thực sự chạy.
- Một starter/thư viện có thể đăng ký custom executor hoặc scheduler; khi đó property không nhất thiết làm bean tùy chỉnh chuyển sang virtual.
- Một chương trình tự gọi `Executors.newFixedThreadPool(8)` vẫn tạo một pool theo code của nó; Boot không tự sửa method call Java đó.
- Chọn Java 21+ và Boot version tương thích; không dùng ví dụ Java 21 để khẳng định nó chạy trên Java 17.

### 3.2. Cấu hình toàn ứng dụng không thay đổi mọi con đường thực thi

`spring.threads.virtual.enabled=true` điều khiển những tích hợp Boot hỗ trợ virtual threads, không phải một “công tắc JVM đổi tất cả Thread thành virtual”.

Ví dụ:

- `@Async` sử dụng executor được Spring lựa chọn; nếu bạn định nghĩa executor riêng, nó có thể là platform-thread pool.
- `@Scheduled` phụ thuộc scheduler được chọn; khi Boot tự cấu hình trên Java 21 với flag bật, đó là `SimpleAsyncTaskScheduler`.
- Servlet container có các đường tích hợp virtual threads tùy loại server/version.
- Spring WebFlux với Reactor Netty vẫn có event-loop model riêng; không biến toàn bộ event loop thành virtual threads.
- Database connection pool như HikariCP quản lý **connections**, không phải số virtual threads.
- Remote service còn có connection/throughput/rate limits riêng.

## 4. Bảng thay đổi đối với các thuộc tính pool của Boot 3.3

Theo danh sách Common Application Properties của Spring Boot 3.3, các thuộc tính sau **không có tác dụng với auto-configured task executor khi virtual threads được bật**:

| Property | Khi dùng `ThreadPoolTaskExecutor` | Khi auto executor dùng virtual threads |
| --- | --- | --- |
| `spring.task.execution.pool.core-size` | Số core worker threads | **Không còn tác dụng** |
| `spring.task.execution.pool.max-size` | Trần worker threads khi điều kiện tăng pool được đáp ứng | **Không còn tác dụng** |
| `spring.task.execution.pool.queue-capacity` | Dung lượng hàng đợi tác vụ | **Không còn tác dụng** |
| `spring.task.execution.pool.keep-alive` | Thời gian giữ worker không hoạt động | **Không còn tác dụng** |
| `spring.task.execution.pool.allow-core-thread-timeout` | Cho phép core worker hết hạn khi rảnh | **Không còn tác dụng** |

Với **auto-configured scheduler**:

| Property | Khi dùng `ThreadPoolTaskScheduler` | Khi dùng `SimpleAsyncTaskScheduler` |
| --- | --- | --- |
| `spring.task.scheduling.pool.size` | Số thread trong scheduler pool | **Không còn tác dụng** |

**Phạm vi của khẳng định “không còn tác dụng”:** các bean auto-configuration tương ứng sau khi Boot chọn `SimpleAsyncTaskExecutor`/`SimpleAsyncTaskScheduler`. Nếu ứng dụng có một executor/scheduler tự tạo, hãy kiểm tra **chính cấu hình của bean đó** và API của implementation; đừng lấy bảng này để tuyên bố mọi pool trong JVM đều bỏ qua cấu hình.

### 4.1. Tại sao max-size có thể đã không đạt hiệu quả ngay cả trước virtual threads?

Ngay trong mô hình `ThreadPoolTaskExecutor` truyền thống, `max-size` **có thể không giới hạn như bạn nghĩ** nếu queue là unbounded. Khi core threads đều bận nhưng hàng đợi vẫn nhận tasks, pool thường không cần tăng đến maximum. Vì vậy thay:

```properties
spring.task.execution.pool.max-size=100
```

mà không xem `queue-capacity` trước đó có thể đã cho kết quả không mong đợi.

Sau khi chuyển sang virtual threads, vấn đề đổi hoàn toàn: `max-size` không điều khiển `SimpleAsyncTaskExecutor` nữa. Khi kiểm tra cấu hình cũ, hãy phân biệt **thuộc tính từng có hiệu quả nhưng giờ bị bỏ qua** với **thuộc tính trước đây vốn không kiểm soát hành vi theo kỳ vọng**.

### 4.2. Cấu hình cũ còn trong file có gây lỗi khởi động không?

Thông thường, việc một property hợp lệ như `spring.task.execution.pool.max-size=16` vẫn tồn tại không nhất thiết gây lỗi startup chỉ vì Boot chọn executor virtual. Điều đáng lo hơn là **nhóm vận hành nghĩ giới hạn 16 vẫn bảo vệ downstream** trong khi nó đã không còn tác dụng với executor auto-config.

Vì vậy audit cấu hình phải xét **semantics runtime**, không chỉ xem startup có lỗi property binding hay không.

## 5. Auto-configured task executor chuyển sang gì?

Spring Boot 3.3 mô tả cơ chế task execution:

- Nếu không có custom `Executor` phù hợp làm auto-configuration rút lui, Boot tự cấu hình một `AsyncTaskExecutor`.
- Khi virtual threads **tắt**, implementation thường là `ThreadPoolTaskExecutor`.
- Khi virtual threads **bật** trên Java 21+, implementation là `SimpleAsyncTaskExecutor` dùng virtual threads.

`AsyncTaskExecutor` tự cấu hình có thể được dùng bởi các tích hợp như:

- `@EnableAsync` / phương thức `@Async` theo quy tắc chọn executor.
- Xử lý async của Spring MVC trong những đường tích hợp phù hợp.
- Một số cơ chế async trong Spring for GraphQL.
- Hỗ trợ thực thi blocking phù hợp trong Spring WebFlux.

**Không phải mọi lời gọi async đều chắc chắn đi qua bean này.** Nếu có bean `Executor` riêng, `AsyncConfigurer`, executor chỉ định bằng qualifier hoặc một framework subsystem khác, quy tắc lựa chọn bean có thể thay đổi.

### 5.1. Cấu hình platform pool truyền thống

```properties
spring.threads.virtual.enabled=false
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=16
spring.task.execution.pool.keep-alive=30s
```

Trong ứng dụng không có custom executor, đây là các thuộc tính dành cho `ThreadPoolTaskExecutor` auto-configured.

Từ góc nhìn thực thi, có thể hình dung:

```text
Tối đa 4 core threads (và khả năng tăng tới 8)
Queue có 16 slots
Các tác vụ thêm có thể bị từ chối khi hết khả năng nhận
```

Đây là mô hình đơn giản. Chính xác khi nào tăng từ core tới maximum phụ thuộc quy tắc `ThreadPoolExecutor`: thông thường core threads được dùng trước, sau đó queue, rồi mới tăng thêm threads nếu queue đã đầy, và sau cùng rejection khi không còn khả năng nhận.

### 5.2. Cấu hình bật virtual threads

```properties
spring.threads.virtual.enabled=true

# Các property pool truyền thống dưới đây không khống chế
# SimpleAsyncTaskExecutor tự cấu hình:
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=16
spring.task.execution.pool.keep-alive=30s
```

**Không nên** giữ bốn thuộc tính trên với chú thích “giới hạn executor ở 8 tác vụ”. Chúng không đưa ra một giới hạn concurrency tương đương khi virtual threads được bật.

Cấu hình rõ ràng hơn:

```properties
spring.threads.virtual.enabled=true
spring.task.execution.simple.concurrency-limit=32
```

`spring.task.execution.simple.concurrency-limit` là thuộc tính mà Spring Boot 3.3 cung cấp cho `SimpleAsyncTaskExecutor`. Nó **giới hạn số thực thi đồng thời** đi qua executor tương ứng; đó là khái niệm **concurrency limiter**, không phải worker thread pool size. Nó cũng không đồng nghĩa giới hạn 32 requests trên toàn bộ ứng dụng nếu có những entry point không dùng executor này.

### 5.3. Giới hạn concurrency của simple executor hoạt động thế nào?

Với `SimpleAsyncTaskExecutor`:

- Implementation không có pool tái sử dụng worker threads kiểu `ThreadPoolTaskExecutor`.
- `setConcurrencyLimit(int)` giới hạn lượng thực thi đồng thời; mặc định thường không giới hạn nếu không được cấu hình.
- Khi đạt giới hạn, chính sách mặc định của cơ chế limit có thể **khiến bên gửi task phải chờ** thay vì tạo thêm task thread ngay. Đừng tự suy luận nó giống một queue bounded và rejection policy cũ.
- Khi tác vụ hoàn tất, slot concurrency được giải phóng.
- Nếu producer gửi task nhanh hơn tốc độ hoàn tất kéo dài, việc chờ và backpressure vẫn cần được giám sát.

**Quan trọng:** concurrency limit không thay được capacity planning của database, HTTP client, CPU hay memory. Một giới hạn 32 tại executor chỉ có hiệu lực với **các task đi qua chính executor đó**.

## 6. Auto-configured scheduler thay đổi thế nào?

Khi sử dụng `@EnableScheduling` và Spring Boot cần auto-configure một scheduler:

- Tắt virtual threads → `ThreadPoolTaskScheduler` (theo cấu hình pool).
- Bật virtual threads → `SimpleAsyncTaskScheduler` dùng virtual threads, không dùng pool scheduler threads truyền thống.

Ví dụ config cũ:

```properties
spring.task.scheduling.pool.size=8
```

Khi `SimpleAsyncTaskScheduler` được chọn, property trên **không tạo ra tám scheduler worker threads**. Đừng kết luận scheduler đang chạy tám scheduled tasks đồng thời chỉ từ dòng này.

### 6.1. Cơ chế SimpleAsyncTaskScheduler

`SimpleAsyncTaskScheduler` của Spring Framework 6.1 có cách hoạt động đặc biệt:

```text
Một scheduler thread điều phối các lần kích hoạt
        |
        +-- fixed-rate/cron task #1 -> execution thread riêng
        +-- fixed-rate/cron task #2 -> execution thread riêng
        +-- fixed-rate/cron task #3 -> execution thread riêng
        |
        +-- fixed-delay tasks -> thực thi trên
                                scheduler thread duy nhất
```

Đối với mô hình có virtual threads, Spring Framework khuyến nghị **fixed rate hoặc cron** thay vì **fixed delay** cho công việc cần khả năng chạy đồng thời. `fixedDelay` trên `SimpleAsyncTaskScheduler` có trường hợp thực thi trên **scheduler thread duy nhất** để giữ semantics fixed delay, có thể gây bottleneck nếu một công việc chặn lâu.

**Không khẳng định mọi task `@Scheduled` tự động chạy song song.** Loại trigger, scheduler bean và cách gọi method quyết định concurrency thực tế.

### 6.2. Thuộc tính simple scheduler

Spring Boot 3.3 còn có:

```properties
spring.task.scheduling.simple.concurrency-limit=16
```

Đây là thuộc tính thuộc nhóm `simple`, không phải `pool`. Nó chỉ có ý nghĩa khi implementation scheduler tương ứng sử dụng cơ chế giới hạn đó; không phải một cam kết rằng mọi cron job hoặc Quartz job trên toàn ứng dụng đều bị giới hạn 16.

Đồng thời, cần kiểm tra `@Scheduled(fixedDelay=...)` vì nó vẫn có đặc tính điều phối riêng trên `SimpleAsyncTaskScheduler`. Một giới hạn concurrency được khai báo không biến fixed delay thành fixed-rate.

### 6.3. Ví dụ hai cách cấu hình

**Platform scheduler:**

```properties
spring.threads.virtual.enabled=false
spring.task.scheduling.pool.size=4
```

**Virtual-thread-aligned scheduler:**

```properties
spring.threads.virtual.enabled=true
spring.task.scheduling.simple.concurrency-limit=16
```

Hai đoạn này là **hai cấu hình để so sánh**, không nên đưa cả hai giá trị `spring.threads.virtual.enabled` vào cùng một file rồi kỳ vọng hành vi rõ ràng. Khi làm benchmark, khởi động hai tiến trình mới với từng cấu hình riêng.

## 7. Ví dụ runnable Java 21 / Spring Boot 3.3: chứng minh loại executor

Phần này cung cấp một ứng dụng nhỏ **không tạo custom Executor bean**, để Spring Boot tự chọn executor. Chúng ta quan sát:

1. Class của bean `applicationTaskExecutor` mà Boot tự cấu hình.
2. `Thread.currentThread().isVirtual()` **ngay bên trong tác vụ** do executor thực thi.

Kết quả không phụ thuộc vào thứ tự nhiều tác vụ vì chỉ có một future và có timeout.

### 7.1. Cấu trúc project

```text
virtual-pool-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          vthreads/
            VirtualPoolApplication.java
      resources/
        application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'virtual-pool-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Cấu hình cần một JDK 21+ và Gradle wrapper tương thích. Phiên bản Spring Boot 3.3.13 được dùng để minh họa các API thuộc nhánh 3.3; không phải gợi ý chọn một bản đã hết hỗ trợ cho dự án mới.

`src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR

spring.threads.virtual.enabled=false

spring.task.execution.pool.core-size=2
spring.task.execution.pool.max-size=4
spring.task.execution.pool.queue-capacity=8
```

### 7.2. Source code đầy đủ

`src/main/java/demo/vthreads/VirtualPoolApplication.java`:

```java
package demo.vthreads;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.AsyncTaskExecutor;

@SpringBootApplication
public class VirtualPoolApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(VirtualPoolApplication.class, args)) {
            // Đóng context sau khi runner kiểm tra xong.
        }
    }

    @Bean
    ApplicationRunner inspect(
            @Qualifier("applicationTaskExecutor")
            AsyncTaskExecutor executor) {

        return args -> {
            System.out.println("executor.type="
                    + executor.getClass().getSimpleName());

            CompletableFuture<Boolean> result =
                    new CompletableFuture<>();

            executor.execute(() -> {
                result.complete(Thread.currentThread().isVirtual());
            });

            boolean virtual = result.get(5, TimeUnit.SECONDS);
            System.out.println("task.isVirtual=" + virtual);
        };
    }
}
```

Chương trình không định nghĩa `Executor` bean tùy chỉnh, nên có thể quan sát auto-configuration mặc định. `AsyncTaskExecutor` hỗ trợ `execute(Runnable)`; `CompletableFuture` chuyển kết quả boolean từ worker về runner theo cách thread-safe và `get(5, TimeUnit.SECONDS)` giúp không chờ vô hạn.

Dùng `try-with-resources` phù hợp vì đây là **CLI demo ngắn**. Trong web service chạy lâu dài, không đóng context ngay sau `run(...)`.

### 7.3. Chạy với platform threads

Với Gradle wrapper có sẵn:

```bash
./gradlew bootRun
```

Các dòng do **code ứng dụng** in ra khi auto-config của demo được giữ nguyên:

```text
executor.type=ThreadPoolTaskExecutor
task.isVirtual=false
```

Có thể có thêm log từ Gradle/Spring. Tên class ở đây là `getSimpleName()` của implementation được Boot chọn. Đây là hành vi của demo với **không custom Executor bean**; đừng áp dụng output đó cho ứng dụng đã thay executor bằng bean riêng.

### 7.4. Chạy với virtual threads

Khởi chạy tiến trình mới:

```bash
./gradlew bootRun --args='--spring.threads.virtual.enabled=true'
```

Khi đó các dòng do code in ra:

```text
executor.type=SimpleAsyncTaskExecutor
task.isVirtual=true
```

**Đây là bằng chứng cần kiểm tra**: class executor đổi và thread thực thi task là virtual. Các thuộc tính `spring.task.execution.pool.*` vẫn có trong file cấu hình nhưng **không dùng để tạo một pool có core=2, max=4, queue=8 cho executor mới**.

Lưu ý Gradle, CMD và PowerShell có quy tắc quoting khác nhau; sửa dấu nháy khi chạy trên shell của mình. Có thể thay trực tiếp property trong file rồi chạy lại nếu không tiện truyền qua `--args`.

### 7.5. Vì sao không in số lượng platform worker từ thread dump rồi kết luận?

Virtual threads được **mount/unmount** lên platform carrier threads theo nhu cầu. Số carrier threads lúc một snapshot được chụp:

- Không bằng số virtual threads đang sống.
- Không phải giới hạn số requests, tasks hoặc database connections.
- Có thể thay đổi theo CPU, tải và hành vi runtime.
- Có thể bị ảnh hưởng bởi blocking/pinning và các hoạt động khác trong JVM.

`Thread.currentThread().isVirtual()` đo **loại thread thực thi tác vụ hiện tại**, còn `executor.getClass()` cho biết **implementation bean**. Hai phép đo kết hợp phù hợp hơn việc chỉ đếm số dòng thread trong log.

## 8. Ví dụ kiểm chứng property pool.size của scheduler không còn ý nghĩa

Nếu muốn nghiên cứu scheduler, tạo một ứng dụng demo độc lập có `@EnableScheduling`, một bean `@Scheduled` và để Boot auto-config scheduler.

Đoạn cấu hình:

```java
@Configuration
@EnableScheduling
class SchedulingConfig {

    @Scheduled(fixedRate = 5000)
    void heartbeat() {
        System.out.println("scheduled.isVirtual="
                + Thread.currentThread().isVirtual());
    }
}
```

Đây là snippet đặt trong class package phù hợp, cần các import:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
```

Thêm một lần vào một project Spring Boot với bean không bị loại bởi scan/conditional configuration. Với `SimpleAsyncTaskScheduler` và virtual threads, **fixed-rate execution** phù hợp với cơ chế thread-per-task. Những dòng `scheduled.isVirtual=...` phụ thuộc thời gian và scheduler thực tế nên **không đưa ra stdout cố định** như demo `ApplicationRunner` ở mục 7.

Thử hai cấu hình:

```properties
# Lần chạy A: platform scheduler
spring.threads.virtual.enabled=false
spring.task.scheduling.pool.size=2
```

```properties
# Lần chạy B: virtual-thread scheduler
spring.threads.virtual.enabled=true
spring.task.scheduling.pool.size=2
```

Với lần B, `pool.size=2` không biến auto scheduler thành hai worker platform threads. Đó là thay đổi bản chất backend scheduler chứ không phải lỗi parsing.

**Không dùng một tác vụ duy nhất để suy ra mức độ song song tối đa.** Muốn kiểm chứng concurrency, cần nhiều trigger/tác vụ hoặc lượng tải được kiểm soát, cùng recorder đo số active tasks tại từng thời điểm.

## 9. Giới hạn concurrency mà không cần thread pool cố định

Một sai lầm khi bật virtual threads là bỏ toàn bộ giới hạn vì “thread rẻ”. Virtual threads giúp việc **đợi I/O** rẻ hơn, nhưng downstream resource vẫn có giới hạn:

```text
10.000 virtual threads
         |
         +-- Database connections: 20
         +-- HTTP client max connections: 100
         +-- Remote service rate limit: 500 requests/minute
         +-- CPU cores: hữu hạn
         +-- Heap / native memory: hữu hạn
         +-- File descriptors: hữu hạn
```

Nếu tất cả 10.000 tác vụ cùng cần database connection, **không phải database tự có 10.000 connection**. Nhiều task sẽ chờ hoặc timeout, và hệ thống có thể tăng memory/latency.

### 9.1. Concurrency limit của Spring Boot

Trong đường auto-config SimpleAsyncTaskExecutor:

```properties
spring.threads.virtual.enabled=true
spring.task.execution.simple.concurrency-limit=32
```

Giới hạn này giúp kiểm soát số task thực thi đồng thời **qua bean task executor tương ứng**. Nó không tự hạn chế:

- Một controller servlet dùng đường dispatch khác.
- Một scheduled task không dùng executor này.
- Code tự gọi `Thread.startVirtualThread(...)`.
- Custom `ExecutorService` không qua bean auto-config.
- JDBC connection pool và các network client.

Vì vậy phải gắn giới hạn đúng **tại nơi task được submit hoặc tại resource cần bảo vệ**.

### 9.2. Semaphore để giới hạn một resource

Một cách giới hạn **concurrent operations** độc lập với executor là dùng `Semaphore`.

Ví dụ Java 21 chạy độc lập, file `PermitDemo.java`:

```java
import java.util.concurrent.Semaphore;

public class PermitDemo {

    private static final Semaphore PERMITS = new Semaphore(2);

    public static void main(String[] args) throws InterruptedException {
        Thread t1 = Thread.ofVirtual().start(() -> guarded("A"));
        Thread t2 = Thread.ofVirtual().start(() -> guarded("B"));
        Thread t3 = Thread.ofVirtual().start(() -> guarded("C"));

        t1.join();
        t2.join();
        t3.join();

        System.out.println("all.done");
    }

    private static void guarded(String name) {
        boolean acquired = false;

        try {
            PERMITS.acquire();
            acquired = true;

            System.out.println("entered=" + name
                    + ", virtual=" + Thread.currentThread().isVirtual());
            Thread.sleep(100);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        } finally {
            if (acquired) {
                PERMITS.release();
            }
        }
    }
}
```

Chạy:

```bash
javac PermitDemo.java
java PermitDemo
```

**Output không có thứ tự cố định** giữa các dòng `entered=A`, `entered=B`, `entered=C`, vì thread scheduling là concurrent. Ba dòng `entered=...` đều cho `virtual=true`, còn dòng cuối là:

```text
all.done
```

Semaphore chỉ cho tối đa **hai task cùng vượt qua `acquire()`** tại một thời điểm. Nó không giới hạn số virtual threads được tạo; task thứ ba có thể đang chờ permit. Vì vậy nếu upstream liên tục tạo thêm virtual threads nhanh hơn downstream xử lý, bạn vẫn cần **backpressure và giới hạn đầu vào**.

Trong production, nên bổ sung deadline, cancellation, metrics, chính sách fairness nếu cần, và kiểm tra exception thực tế của operation. `Thread.sleep(100)` chỉ mô phỏng một thao tác chờ trong demo, không phải mẫu gọi I/O production.

### 9.3. Không dùng pool platform threads như semaphore thay thế một cách vô thức

Trước đây có ứng dụng **dựa vào maxPoolSize=16** để “mặc nhiên” giới hạn số request gửi tới một API. Khi chuyển sang virtual-thread-per-task, hàng rào này biến mất nếu chỉ nằm ở `spring.task.execution.pool.max-size`.

Giải pháp cần thiết kế lại:

- Dùng concurrency limiter/`Semaphore` gắn với API đó.
- Dùng rate limiter khi hệ thống ngoài giới hạn **requests/second** chứ không phải đồng thời.
- Dùng bounded queue và rejection/backpressure nếu lưu lượng vào lớn hơn lưu lượng phục vụ.
- Đặt connection pool size, timeout và retry policy phù hợp với service phụ thuộc.
- Giám sát số task active và số task đang đợi permit, không chỉ đếm JVM threads.

## 10. Thread pool truyền thống nào vẫn còn hiệu lực?

**Không phải mọi nhóm luồng đều biến mất**. Bảng sau là điểm quan trọng khi audit ứng dụng:

| Thành phần | Khi bật virtual threads ở Boot | Kết luận về tuning |
| --- | --- | --- |
| Auto `applicationTaskExecutor` | Thường dùng `SimpleAsyncTaskExecutor` virtual | `spring.task.execution.pool.*` không còn áp dụng |
| Auto scheduler khi cần | Thường dùng `SimpleAsyncTaskScheduler` virtual | `spring.task.scheduling.pool.size` không còn áp dụng |
| Custom `ThreadPoolTaskExecutor` | Vẫn là bean do ứng dụng tạo trừ khi bạn tự thay | `corePoolSize`/`maxPoolSize` của **custom bean** vẫn có thể hiệu lực |
| Custom `ThreadPoolTaskScheduler` | Không bị Boot tự thay chỉ vì global virtual flag | Cấu hình pool của **custom scheduler** vẫn có thể hiệu lực |
| `Executors.newFixedThreadPool(n)` | Tạo platform thread pool theo code | `n` vẫn có ý nghĩa |
| `Executors.newVirtualThreadPerTaskExecutor()` | Mỗi task có virtual thread | Không có pool size n truyền thống |
| HikariCP | Quản lý database connection | `maximumPoolSize` là số connection, vẫn cần tuning |
| HTTP client connection pool | Quản lý kết nối/tốc độ tới server khác | Giới hạn connection vẫn áp dụng |
| Reactor Netty event loops | Mô hình event-loop độc lập | Không tự chuyển thành virtual-thread-per-task chỉ nhờ flag |
| Rate limiter / semaphore | Kiểm soát số việc vào tài nguyên | Vẫn cần để bảo vệ downstream |
| CPU-bound worker pool | Tùy executor cụ thể | Nhiều virtual threads không tạo thêm CPU cores |

Bảng phản ánh **mô hình cấu hình**, không có ý định áp một kết luận tương tự cho mọi thư viện server/client. Với từng component, hãy kiểm tra class executor ở runtime và tài liệu đúng version.

### 10.1. Ví dụ custom ThreadPoolTaskExecutor

```java
@Configuration
class CustomExecutorConfig {

    @Bean("legacyExecutor")
    ThreadPoolTaskExecutor legacyExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("legacy-");

        return executor;
    }
}
```

Snippet này cần import `Configuration`, `Bean` và `ThreadPoolTaskExecutor`. Khi Spring quản lý lifecycle của bean, implementation có thể initialize qua cơ chế bean factory tương ứng.

**Chú ý:** chỉ vì `spring.threads.virtual.enabled=true`, bean này **không tự biến thành SimpleAsyncTaskExecutor**. Nó vẫn là custom `ThreadPoolTaskExecutor` với một pool có thể cấu hình.

Một số auto-config của Spring Boot có quy tắc lùi khi có `Executor` bean tùy chỉnh. Vì vậy chỉ thêm đoạn cấu hình này có thể **làm thay đổi bean auto task executor** và cách `@Async` chọn executor. Đừng cấy nó vào demo mục 7 khi mục tiêu là quan sát auto-config mặc định.

### 10.2. JDBC connection pool không phải thread pool

Ví dụ:

```properties
spring.datasource.hikari.maximum-pool-size=20
```

Thuộc tính này giới hạn **database connections trong HikariCP** khi Hikari được cấu hình, không giới hạn số virtual threads. Một connection bị chiếm lâu vẫn làm task khác chờ. Nếu application tạo 5.000 virtual threads đồng thời truy vấn database, throughput có thể bị bottleneck ở 20 connections (cộng những giới hạn database), chứ không vì virtual threads mà pool connection tự mở rộng vô hạn.

Hãy theo dõi:

- Active/idle/pending connections.
- Thời gian chờ mượn connection.
- SQL query latency và transaction duration.
- Timeout, retry và hiện tượng nhiều task cùng chờ database.
- Số concurrent requests thực tế qua service.

**Không nhầm** `spring.datasource.hikari.maximum-pool-size` với `spring.task.execution.pool.max-size`. Một cái giới hạn connection; cái kia trước đây giới hạn một implementation thread executor.

## 11. Servlet server: đừng áp công thức chung lên Tomcat/Jetty/Undertow

Một số cấu hình server dùng tên “threads”:

```properties
server.tomcat.threads.max=200
server.tomcat.threads.min-spare=10
```

Trong mô hình Tomcat platform executor truyền thống, các giá trị này phục vụ việc điều chỉnh pool xử lý request. Khi dùng virtual-thread integration của Spring Boot/Tomcat phù hợp, request execution có thể đi qua virtual-thread executor, nên **các giới hạn worker platform-thread truyền thống không còn mô tả số virtual requests được phép** theo cách cũ.

Nhưng cần tránh khẳng định một chiều rằng **mọi `server.*.threads.*` đều luôn bị bỏ qua**:

- Điều đó còn phụ thuộc server thật sự đang chạy (Tomcat/Jetty/Undertow/khác).
- Phụ thuộc phiên bản Boot và embedded-server.
- Phụ thuộc việc ứng dụng có custom connector hoặc executor hay không.
- Có thể có bộ phận acceptor, poller, selector, event loop hoặc I/O workers vẫn là platform threads.
- Có thể có giới hạn `max-connections`, request queue, timeout hoặc connector-specific còn hiệu lực.

**Đúng cách:** xác định server, executor của connector, runtime version và đo thực tế. Không đưa ra một khuyến nghị “xóa toàn bộ cấu hình server threads” chỉ dựa vào global flag.

### 11.1. WebFlux và event loops

Reactor Netty dùng event loops. Khi bật `spring.threads.virtual.enabled`, đừng coi toàn bộ pipeline reactive đã đổi sang một virtual thread cho mỗi request. Tích hợp blocking execution có thể dùng Boot task executor ở những điểm hỗ trợ, nhưng event-loop architecture là chuyện khác.

Nếu đang dùng reactive non-blocking đúng cách, tối ưu thread-per-request không phải lý do để thay toàn bộ mô hình. Ngược lại, nếu đưa blocking JDBC hoặc REST call vào event-loop thread mà không có offload phù hợp, bật virtual threads **không tự sửa lỗi blocking event loop**.

### 11.2. Request concurrency vẫn phải có hàng rào

Dù request xử lý bởi virtual threads, một service vẫn có thể cần:

- Giới hạn request in-flight theo endpoint.
- Hạn mức kết nối TCP và HTTP.
- Rate limit theo client và downstream.
- Circuit breaker/bulkhead.
- Timeout tổng và timeout từng thao tác I/O.
- Quotas đối với workload CPU/heap.
- Cơ chế từ chối hoặc chậm nhận request khi hệ thống đã bão hòa.

Một thread rẻ không biến database query hoặc remote API call thành miễn phí.

## 12. Tại sao giữ max-size cũ có thể làm hệ thống quá tải?

Giả sử trước đây hệ thống có:

```properties
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
```

Team nghĩ đây là một “bulkhead” tối đa 16 tác vụ đồng thời gửi sang downstream. Sau khi bật:

```properties
spring.threads.virtual.enabled=true
```

nếu `@Async` thực sự sử dụng auto-configured `SimpleAsyncTaskExecutor`, pool settings trên không bảo vệ downstream nữa.

Giả sử một đợt spike gửi 2.000 tasks, mỗi task gọi HTTP service:

```text
TRƯỚC:
  Executor platform-thread pool
  -> có thể dùng tối đa một số worker hữu hạn
  -> queue/rejection theo cấu hình

SAU:
  Virtual thread-per-task executor
  -> có thể tạo nhiều virtual tasks hơn
  -> nhiều calls đồng thời hơn nếu không giới hạn mới
  -> downstream bị nghẽn hoặc trả 429/503/timeout
```

Đây là **tình huống minh họa**, không phải cam kết mọi ứng dụng sẽ đạt 2.000 calls đồng thời: client connection pool và các giới hạn khác còn có thể can thiệp.

**Bài học:** khi xóa giới hạn vật lý của thread pool, bạn phải quyết định **giới hạn kinh doanh/hạ tầng** nên nằm ở đâu. Có thể dùng `spring.task.execution.simple.concurrency-limit` hoặc giới hạn riêng của từng downstream.

## 13. CPU-bound và I/O-bound: chọn cách tune theo nút thắt

### Công việc I/O-bound

Ví dụ:

- Gọi database và chờ truy vấn.
- Gọi API ngoài và chờ network response.
- Đọc file theo API blocking phù hợp.
- Chờ message hoặc kết quả từ hệ thống ngoài.

Virtual threads thường phù hợp với coding style blocking tuần tự cho các tác vụ như vậy. Tuy nhiên **thông lượng vẫn bị giới hạn** bởi DB, HTTP client, network, rate limit, timeout và bên phục vụ.

### Công việc CPU-bound

Ví dụ:

- Mã hóa/giải mã nặng.
- Resize ảnh, xử lý số liệu lớn.
- Tính toán thuật toán.
- Transform dữ liệu thuần CPU.

Nếu CPU có 8 cores và có 5.000 tác vụ cùng chạy tính toán, virtual threads không tạo thêm CPU. Một **bounded CPU executor** hoặc cơ chế giới hạn công việc theo CPU vẫn có thể thích hợp.

Không có công thức kiểu “virtual threads thì set max-size=1.000.000” cho mọi workload. Hãy đo và phân loại workload trước.

### Pinning trong Java 21

Virtual thread có thể bị **pinned** vào carrier thread trong một số đoạn thực thi, ví dụ vùng `synchronized` trong điều kiện đặc thù hoặc native/foreign code. Khi pinned và gặp blocking, carrier không được giải phóng như mong đợi, làm giảm hiệu quả concurrency.

Trên Java 21, nên dùng JFR event liên quan virtual-thread pinning và công cụ chẩn đoán JVM thích hợp để xác định điểm nghẽn. Không tự kết luận cứ thêm virtual threads sẽ tăng throughput. Các phiên bản Java mới hơn có thể thay đổi tình trạng pinning, nên khi nâng cấp cần đọc tài liệu JVM tương ứng.

## 14. Bảng cấu hình: cái gì nên giữ, bỏ, đổi?

| Cấu hình | Hành động khi chuyển auto task sang virtual |
| --- | --- |
| `spring.task.execution.pool.core-size` | Bỏ khỏi mô tả giới hạn executor virtual; giữ chỉ nếu còn một pool thực sự cần property đó |
| `spring.task.execution.pool.max-size` | Không coi là bulkhead nữa; thay bằng concurrency limit phù hợp |
| `spring.task.execution.pool.queue-capacity` | Không coi là bounded queue của SimpleAsyncTaskExecutor |
| `spring.task.execution.pool.keep-alive` | Không tune lifecycle virtual thread bằng property này |
| `spring.task.execution.pool.allow-core-thread-timeout` | Không áp dụng cho simple executor virtual |
| `spring.task.scheduling.pool.size` | Không tune SimpleAsyncTaskScheduler bằng property này |
| `spring.task.execution.simple.concurrency-limit` | Cân nhắc nếu muốn giới hạn tasks qua auto simple executor |
| `spring.task.scheduling.simple.concurrency-limit` | Cân nhắc nếu cần giới hạn thực thi của simple scheduler |
| `spring.task.execution.thread-name-prefix` | Có thể vẫn hữu ích cho nhận diện tasks, không phải pool size |
| `spring.main.keep-alive` | Cân nhắc cho ứng dụng chỉ còn daemon virtual threads và cần sống lâu |
| `spring.datasource.hikari.maximum-pool-size` | **Vẫn cần** tune theo database capacity |
| HTTP client pool size | **Vẫn cần** tune theo downstream capacity |
| Custom `ThreadPoolTaskExecutor` props | **Vẫn có ý nghĩa** cho custom executor đó, nếu được dùng |

Không nên chỉ “xóa hết dòng pool.* cho file gọn” mà chưa lập bản đồ executor/scheduler thực tế. Trong một ứng dụng lớn, có thể có nhiều thread pools từ thư viện, mỗi pool có policy riêng.

## 15. Cách kiểm chứng cấu hình đã có tác dụng thật

Đừng chỉ nhìn file properties. Cần quan sát **implementation** và **hành vi**.

### 15.1. Kiểm tra executor bean thật

Trong context phù hợp:

```java
AsyncTaskExecutor executor = context.getBean(
        "applicationTaskExecutor", AsyncTaskExecutor.class);

System.out.println(executor.getClass().getName());
```

Đây là **snippet trong method** có biến `context` đã được tạo và import `AsyncTaskExecutor`. Nếu một app không có bean tên `applicationTaskExecutor` do custom config, lời gọi sẽ thất bại; đó là tín hiệu cần kiểm tra selection, không phải lỗi virtual threads của Java.

### 15.2. Kiểm tra loại thread trong công việc thật

```java
executor.execute(() -> {
    boolean virtual = Thread.currentThread().isVirtual();
    System.out.println("isVirtual=" + virtual);
});
```

Đây là snippet trên Java 21+, có `executor` kiểu `AsyncTaskExecutor` hoặc `Executor` được truyền vào. Không thực thi đoạn này trên Java 17 nếu method `Thread.isVirtual()` không tồn tại.

### 15.3. Quan sát limit thực sự

Đo:

- Số task đang được thực thi và số task đang đợi submit/permit.
- Thời gian chờ trước khi tác vụ bắt đầu.
- Rejection, timeout và cancellation.
- Hikari active/pending connections.
- HTTP client leased/idle connections.
- Request latency P95/P99 và error rate.
- CPU utilization, memory footprint, GC và tình trạng pinning.
- Startup/shutdown của scheduler và executor.

Nếu property `max-size=16` được giữ nhưng số active tasks qua auto virtual executor lên trên 16 trong test đo đúng, đây là **hành vi đúng** theo backend đã chuyển, không phải lỗi binding.

### 15.4. Hai cấu hình, hai tiến trình riêng

Khi benchmark:

1. Chạy baseline với `spring.threads.virtual.enabled=false`.
2. Ghi loại executor/scheduler, số task active, throughput và latency.
3. Đóng hẳn ứng dụng.
4. Chạy lại với `true` trên Java 21+.
5. Kiểm tra class executor/scheduler và `Thread.isVirtual()` trước khi so kết quả.
6. Giữ ổn định workload, JVM flags, kết nối DB, CPU, heap và traffic.
7. Không so startup log của lần A với load test hoàn toàn khác của lần B.

Khi một benchmark có thêm custom Executor trong lần B, bạn không còn đang so **cùng một cấu hình** chỉ khác virtual flag nữa.

## 16. Những bẫy với @Async

Một class có method:

```java
@Service
public class ImportService {

    @Async
    public void importFile() {
        System.out.println("async.isVirtual="
                + Thread.currentThread().isVirtual());
    }
}
```

Đoạn này cần import `Service`, `Async` và config `@EnableAsync` thích hợp; file `ImportService.java` riêng, compile bằng Java 21+.

Khi không có custom executor, `@Async` có thể dùng executor do Boot auto-config. Nhưng có các trường hợp không giống demo:

- `@Async("specialExecutor")` chọn executor khác nếu bean tồn tại.
- `AsyncConfigurer#getAsyncExecutor()` có thể chỉ định executor riêng.
- Nhiều `Executor` beans làm logic chọn bean thay đổi.
- **Self-invocation**: gọi method `@Async` từ method khác trên **cùng instance** có thể bypass Spring AOP proxy, khiến method chạy đồng bộ ngay trên caller thread.
- Một bean không do Spring quản lý không tự nhận proxy `@Async`.
- Không phải mọi ứng dụng tích hợp async đều chạy qua `applicationTaskExecutor` theo cùng quy tắc.

**Sai lầm cần tránh:** “`spring.threads.virtual.enabled=true` rồi thì mọi method `@Async` chắc chắn chạy virtual.” Hãy kiểm tra executor thực tế và cách lời gọi đi qua proxy.

## 17. Những bẫy với @Scheduled và fixedDelay

Dùng Spring Boot virtual scheduler không chỉ đổi tên thread. Cách hoạt động của `SimpleAsyncTaskScheduler` khác `ThreadPoolTaskScheduler`, đặc biệt:

```java
@Scheduled(fixedDelay = 1000)
public void pollQueue() {
    // Có thể block trong khi chạy trên scheduler thread
    // khi dùng SimpleAsyncTaskScheduler.
}
```

Đây là method snippet, cần `@EnableScheduling` trong config, bean Spring thích hợp và import `Scheduled`.

Trong mô hình này, fixed-delay task được thực thi trên một scheduler thread duy nhất, nên một task chậm có thể ảnh hưởng scheduling. Nếu tác vụ cần thread-per-task concurrency, Spring Framework khuyến nghị fixed-rate hoặc cron khi dùng SimpleAsyncTaskScheduler virtual.

Tuy nhiên **đổi fixedDelay thành fixedRate không phải thay đổi vô hại**. Ngữ nghĩa thay đổi:

- `fixedDelay`: đợi một khoảng sau khi lần trước hoàn tất.
- `fixedRate`: kích hoạt theo khoảng thời gian từ đầu/lịch chạy.
- Nếu mỗi lần chạy lâu hơn chu kỳ, có thể tăng số tác vụ overlap (tùy scheduler/trigger semantics), gây quá tải downstream hoặc lặp xử lý dữ liệu.
- Cron cũng có đặc tính lịch riêng, không mặc định giải quyết idempotency hoặc số lần thực thi.

Khi refactor, cần xác định việc chạy chồng nhau có an toàn không, và thêm single-flight lock, distributed lock hoặc concurrency limit nếu nghiệp vụ yêu cầu.

## 18. Thiết kế giới hạn theo tài nguyên thay vì theo số thread

Một service có thể cần nhiều giới hạn khác nhau:

```text
Incoming HTTP requests
       |
       +-- Admission control / rate limiter
       |
       v
Virtual-thread execution
       |
       +-- CPU-intensive work? -> bounded CPU capacity
       |
       +-- DB call? -> Hikari pool + timeout
       |
       +-- External API? -> HTTP client pool + bulkhead/rate limit
       |
       +-- File I/O? -> file descriptors + disk throughput
       |
       v
Response
```

**Nguyên tắc:** hệ thống cần giới hạn ở **nút thắt và ranh giới sở hữu tài nguyên**. Thread pool truyền thống có thể đã vô tình thực hiện vai trò admission control, nhưng virtual threads tách hai chức năng đó ra.

Đối với từng downstream, trả lời:

1. Tối đa bao nhiêu operations đồng thời là an toàn?
2. Có rate limit theo giây/phút không?
3. Khi hết capacity thì chờ, từ chối hay shed load?
4. Có timeout và cancellation không?
5. Có retry và backoff không? Retry có tạo bão lưu lượng không?
6. Khi client disconnect, tác vụ còn phải chạy không?
7. Khi shutdown, còn bao nhiêu tác vụ chưa hoàn tất và có cần drain không?
8. Metrics nào xác nhận giới hạn đang thực sự được áp dụng?

Chỉ khi trả lời xong mới lựa chọn limiter và giá trị cụ thể. Không có một cấu hình universal đúng cho mọi workload.

## 19. Nếu vẫn cần cố định số worker thì sao?

Không có quy định bắt buộc **mọi tác vụ** phải chạy trên virtual threads. Với CPU-bound hoặc tài nguyên cần dedicated platform threads, custom bounded executor vẫn hợp lý.

Ví dụ:

```java
@Bean("cpuExecutor")
ExecutorService cpuExecutor() {
    return Executors.newFixedThreadPool(
            Runtime.getRuntime().availableProcessors());
}
```

Đây là snippet trong class `@Configuration`, cần import `Bean`, `Executors`, `ExecutorService` và cấu hình lifecycle/close phù hợp. Tại Java 21, `ExecutorService` hỗ trợ `close()` theo hợp đồng `AutoCloseable`; khi đăng ký bean qua `@Bean`, cần đảm bảo container đóng tài nguyên hoặc khai báo `destroyMethod = "close"` nếu muốn tường minh.

Mục đích là tạo **platform thread pool có giới hạn** cho công việc CPU-bound riêng. Nếu bạn đưa custom `ExecutorService` này vào context, nó có thể ảnh hưởng auto-config executor theo condition của Boot; nên cẩn thận lựa chọn bean name, `@Qualifier` và semantics `@Async`.

Điều không đúng là coi custom pool này “mâu thuẫn” với virtual threads. Trong cùng một JVM, **các executor khác nhau có thể dùng những mô hình concurrency khác nhau**.

## 20. Kích thước carrier-thread pool có điều chỉnh giống pool-size không?

Không. Virtual threads được JVM scheduling trên platform carrier threads dùng chung. Việc Java hỗ trợ các tham số JVM liên quan virtual-thread scheduler **không đồng nghĩa** với việc dùng `spring.task.execution.pool.max-size` để điều chỉnh carrier scheduler.

Nếu đo được bottleneck rõ ràng ở scheduler, có thể nghiên cứu các JVM system properties như `jdk.virtualThreadScheduler.parallelism` trên phiên bản JDK hỗ trợ. Nhưng đó là **tuning nâng cao ở tầng JVM**, có hệ quả khác và không nên coi là bản thay thế một-một cho `core-size`/`max-size` của từng executor Spring.

Đặc biệt:

- Đừng tăng carrier parallelism chỉ để “cho nhiều request hơn” khi bottleneck thực sự nằm ở database.
- Đừng giảm parallelism nhằm bảo vệ một remote API; dùng rate/concurrency limiter đúng nơi.
- Đừng đổi JVM scheduler trên production khi chưa benchmark và đo pinning/blocking.
- JDK 21 và các phiên bản sau có thể khác về hành vi virtual-thread pinning và scheduler internals; dùng tài liệu đúng version.

## 21. Khi nào property cũ thực sự vẫn có hiệu lực?

Ví dụ có hai executor:

```text
applicationTaskExecutor  -> SimpleAsyncTaskExecutor (virtual)
legacyExecutor           -> ThreadPoolTaskExecutor (platform)
```

Nếu bạn điều chỉnh `legacyExecutor.setMaxPoolSize(8)` bằng code hoặc bind properties riêng của nó, **custom pool vẫn giới hạn worker** theo thiết kế. Nhưng `spring.task.execution.pool.max-size=8` không tự động đi điều chỉnh tất cả custom executor, và cũng không giới hạn `applicationTaskExecutor` virtual.

Tình huống dễ gây nhầm:

```properties
spring.threads.virtual.enabled=true
spring.task.execution.pool.max-size=8
```

Team thấy CPU-bound tasks vẫn chỉ chạy 8 platform threads, rồi kết luận `pool.max-size` còn hiệu lực với virtual threads. Thực tế chúng có thể đang chạy qua một custom pool 8 threads không liên quan tới property trên.

Cách kiểm chứng đúng:

1. Liệt kê bean `Executor` / `AsyncTaskExecutor` thực sự có.
2. Kiểm tra tên và class mỗi bean.
3. Xem `@Async`/controller/scheduler/SDK đang chọn bean nào.
4. Kiểm tra thread thực thi bằng `Thread.isVirtual()` tại đúng vị trí.
5. Chỉ kết luận một property có tác dụng nếu có đo đạc trước/sau **trên chính bean và đường tác vụ đó**.

## 22. Các thông số khác vẫn hữu ích ở task execution

Không phải toàn bộ namespace `spring.task.execution.*` đều vô nghĩa. Ví dụ:

```properties
spring.task.execution.thread-name-prefix=task-
spring.task.execution.simple.concurrency-limit=32
```

Khi implementation hỗ trợ, thread name prefix có thể giúp quan sát trong logs/traces, còn concurrency limit có thể được dùng để hạn chế song song.

Tuy vậy:

- **Thread name prefix** không phải giới hạn concurrency.
- **Concurrency limit** không đồng nghĩa queue-capacity hoặc max-size.
- **Shutdown properties** cần được xem xét theo implementation, version và task lifecycle; không suy diễn behavior của `ThreadPoolTaskExecutor` sang `SimpleAsyncTaskExecutor`.
- Các task đã được submit có thể đang chờ limiter hoặc I/O; khi context đóng cần chính sách cancellation/drain rõ.
- Một virtual thread đang bị block không có nghĩa đã hoàn tất; lifecycle và timeout vẫn áp dụng.

Cần đối chiếu danh sách property của **Spring Boot 3.3** thay vì trộn thuộc tính mới xuất hiện ở những bản Boot sau vào tài liệu cũ.

## 23. Cách xây bài benchmark có ý nghĩa

Giả định một endpoint gọi API downstream cần 200 ms I/O, còn CPU cần 2 ms. Khi dùng platform pool 16 threads, throughput có thể bị giới hạn bởi số threads giữ chờ; khi dùng virtual threads, phần chờ không nhất thiết chiếm carrier thread.

Nhưng kết quả phụ thuộc:

- Pool connections của HTTP client.
- Rate limit downstream.
- Network stack.
- Database transactions khác trong request.
- JVM GC và memory.
- Tần suất tạo/xử lý tasks.
- Pinning/blocking không unmount được.
- Số CPU thực tế.
- Backpressure và retry.

**Không hứa tăng hiệu năng theo một hệ số cố định.** Những con số 16 threads hoặc 200 ms ở đây chỉ là dữ liệu giả lập để định hướng test.

### Quy trình benchmark

1. Chạy cùng một binary trên JDK hỗ trợ.
2. Test baseline (virtual=false) và virtual=true bằng **hai tiến trình mới**.
3. Ghi chính xác executor class/task virtual state.
4. Cố định pool DB/HTTP và request concurrency trong phép so đầu tiên.
5. Sau đó mới thay đổi admission limit và connection pools theo từng biến riêng.
6. Đo throughput, P50/P95/P99 latency, error rate, timeouts, memory, CPU và GC.
7. Kiểm tra pinning và task queuing/wait.
8. Tăng tải tới ngưỡng lỗi để xem hệ thống **shed load** thế nào, không chỉ đo điểm đẹp nhất.
9. Tái hiện shutdown khi có tasks in-flight.
10. Ghi lại các cấu hình legacy còn tồn tại nhưng đã mất tác dụng đối với auto beans.

Nếu không đo **error rate** và **downstream saturation**, số request xử lý được trong benchmark ngắn có thể che rủi ro làm service phụ thuộc quá tải.

## 24. Vấn đề daemon threads và keep-alive

Virtual threads là daemon threads. Một ứng dụng non-web có `@Scheduled` nhưng không có thread non-daemon khác có thể kết thúc JVM bất ngờ khi main thread xong, ngay cả khi ta mong scheduled tasks giữ process sống.

Spring Boot có:

```properties
spring.main.keep-alive=true
```

để giúp JVM tiếp tục sống trong trường hợp chỉ còn virtual threads. Điều này **khác với kích thước thread pool** nhưng là tác động vận hành khi thay scheduler từ platform sang virtual threads.

Trong demo CLI mục 7, `main` dùng `try-with-resources` để đóng context sau runner; không đặt keep-alive vì muốn chương trình tự kết thúc. Trong service scheduled long-running, hãy xác định rõ trách nhiệm giữ process sống.

Không coi keep-alive là công cụ bảo đảm tasks hoàn tất trong shutdown; muốn graceful shutdown phải cấu hình và implement lifecycle phù hợp.

## 25. Lỗi thường gặp và hướng khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `max-size=16` nhưng thấy hơn 16 virtual tasks | SimpleAsyncTaskExecutor không dùng pool max-size | Dùng `spring.task.execution.simple.concurrency-limit` hoặc limiter ở resource |
| `queue-capacity=100` nhưng không có queue mong đợi | Auto executor đã chuyển sang simple | Thiết kế bounded admission/backpressure mới |
| `core-size` đổi nhưng startup/throughput không đổi | Virtual executor không có core worker pool | Đo implementation rồi loại property không áp dụng |
| `keep-alive` không ảnh hưởng executor | Không còn ThreadPoolTaskExecutor auto | Phân biệt keep-alive của pool và `spring.main.keep-alive` của JVM |
| `spring.task.scheduling.pool.size=8` nhưng scheduled concurrency khác | Auto scheduler là SimpleAsyncTaskScheduler | Dùng simple concurrency policy, xem trigger |
| `fixedDelay` chậm khiến job khác trễ | Fixed-delay chạy trên scheduler thread duy nhất | Xem xét fixed-rate/cron có kiểm soát |
| Bật flag nhưng task không phải virtual | Custom Executor, AsyncConfigurer, sai JVM/config hoặc self-invocation | Kiểm tra bean selection và `Thread.isVirtual()` |
| Tất cả tasks virtual nhưng DB vẫn nghẽn | JDBC connections vẫn hữu hạn | Theo dõi Hikari metrics, timeout và query cost |
| CPU luôn 100%, tăng tasks không cải thiện | CPU-bound workload | Dùng bounded CPU executor, tối ưu thuật toán |
| HTTP client trả 429 nhiều hơn | Mất bulkhead của pool truyền thống | Rate limit/concurrency limit theo downstream |
| Ứng dụng tự thoát khi chỉ có scheduler | Virtual daemon threads không giữ JVM | Xem `spring.main.keep-alive` và đường lifecycle |
| App chậm khi shutdown | Tasks không được drain/cancel phù hợp | Thiết kế shutdown và kiểm tra timeout |
| Thread dump có ít carrier nhưng rất nhiều tasks | Mô hình mount/unmount virtual threads | Không dùng carrier count làm task count |
| `@Async` chạy đồng bộ trên caller | Self-invocation hoặc proxy không có hiệu lực | Gọi qua Spring proxy hoặc refactor bean |
| Servlet vẫn có platform threads | Server internals/custom connector còn platform | Kiểm tra đúng executor và server version |
| Reactor Netty vẫn dùng event-loop threads | WebFlux reactive stack riêng | Không suy diễn global flag đổi mọi event loop |
| Heap tăng dù số platform threads ít | Quá nhiều virtual tasks chờ/giữ state | Bound admissions, giảm retained data và timeout |
| Boot property và custom executor trùng tên | Property auto-config không áp dụng custom bean | Kiểm tra bean implementation & binding |

Một quy trình gỡ lỗi hữu ích:

1. Kiểm tra `java -version` của process.
2. Xác nhận `spring.threads.virtual.enabled` **ở runtime thực**, không chỉ trong file nguồn.
3. Liệt kê `Executor` và `TaskScheduler` beans, tìm custom beans.
4. Kiểm tra class executor/scheduler và type của thread thực thi.
5. Xác định những `pool.*` nào thuộc auto-config bean đã được thay thế.
6. Xác định limits vốn nằm ở thread pool cũ để tái thiết kế admission.
7. Kiểm tra downstream pools, timeouts, rate limits và CPU/memory.
8. Kiểm tra `@Scheduled` fixed-delay behavior nếu jobs chậm.
9. Kiểm tra lifecycle khi chỉ còn daemon virtual threads.
10. Đo lại performance trước khi quyết định thay đổi cấu hình production.

## 26. Bài tập thực hành

### Bài 1: dự đoán executor class

Với cấu hình:

```properties
spring.threads.virtual.enabled=false
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
```

Trong app không custom Executor bean, `applicationTaskExecutor` mặc định thuộc loại nào?

**Đáp án:** `ThreadPoolTaskExecutor` theo auto-config Boot 3.3.

### Bài 2: bật virtual mà giữ pool properties

Chỉ thay `spring.threads.virtual.enabled=true`. Những property `pool.core-size` và `pool.max-size` có giới hạn số virtual tasks bằng 8 không?

**Đáp án:** không. Boot chuyển auto executor sang `SimpleAsyncTaskExecutor` virtual; các property pool trên không còn hiệu lực với bean đó.

### Bài 3: phân biệt concurrency limit với pool size

Đặt:

```properties
spring.threads.virtual.enabled=true
spring.task.execution.simple.concurrency-limit=12
```

Hỏi:

1. Điều gì bị giới hạn?
2. Có phải JVM chỉ tạo tối đa 12 virtual threads không?
3. Một đoạn `Thread.startVirtualThread(...)` tự gọi có bị tính vào cùng giới hạn không?

**Đáp án:** giới hạn áp dụng cho những tasks đi qua simple executor tương ứng; không phải giới hạn virtual threads của toàn JVM. Code tự tạo thread không mặc nhiên chịu cùng limiter.

### Bài 4: scheduler fixed delay

Bật `SimpleAsyncTaskScheduler`, đặt `spring.task.scheduling.pool.size=8` và viết một `@Scheduled(fixedDelay=...)` chặn lâu. Vì sao task vẫn có thể gây nghẽn scheduler dù “pool.size=8”?

**Đáp án:** pool.size không áp dụng cho simple scheduler; hơn nữa fixed-delay tasks có thể chạy trên scheduler thread duy nhất. Cần xem lại scheduling semantics và thiết kế concurrency.

### Bài 5: connection pool

Một app có 2000 virtual tasks gọi database, nhưng Hikari tối đa 20 connections. Điều gì xảy ra nếu tất cả tasks muốn giữ connection đồng thời?

**Đáp án:** chúng không tự tạo thành 2000 DB connections. Những task không lấy được connection sẽ chờ/timeout theo policy của pool, có thể tăng latency, memory và lỗi. Cần giới hạn in-flight database operations và tối ưu query/transaction.

### Bài 6: custom executor

Ứng dụng tự khai báo `ThreadPoolTaskExecutor` max 8 rồi bật global virtual flag. Executor tùy chỉnh có tự chuyển thành virtual không? **Không**. Cần thay implementation hoặc cấu hình riêng nếu muốn virtual threads.

### Bài 7: so sánh hai lần chạy

Chạy demo `VirtualPoolApplication` mục 7 với virtual false và true. Xác nhận:

```text
false: executor.type=ThreadPoolTaskExecutor
       task.isVirtual=false

true:  executor.type=SimpleAsyncTaskExecutor
       task.isVirtual=true
```

Các nhãn `false:` / `true:` ở đây chỉ **đánh dấu hai lượt chạy**, không phải những chữ được code in ra. Mỗi lần code chỉ in hai dòng `executor.type=...` và `task.isVirtual=...`.

### Bài 8: viết quyết định tuning

Cho một service có 8 CPU cores, Hikari 20, HTTP client max 100 connections và nhiều `@Async` tasks. Hãy chọn:

- Dùng bounded CPU pool cho công việc tính toán nào?
- Có cần `spring.task.execution.simple.concurrency-limit` không?
- Có giới hạn riêng cho database/API không?
- Đặt timeout và retry ra sao?
- Đo metrics gì trước/sau?

Mục tiêu là **đưa ra kế hoạch giới hạn theo tài nguyên thật**, không cố tìm một con số `pool.max-size` mới để áp vào mọi subsystem.

## 27. Checklist migration từ platform pool sang virtual threads

- [ ] Runtime thật là Java 21+.
- [ ] Spring Boot version hỗ trợ và flag `spring.threads.virtual.enabled` đã được xác nhận ở runtime.
- [ ] Đã liệt kê executor/scheduler auto-config và custom beans.
- [ ] Không nhầm namespace `spring.task.execution.pool.*` với `spring.task.execution.simple.*`.
- [ ] Các property pool truyền thống không còn được mô tả như giới hạn khi auto-config đổi sang simple executor.
- [ ] Đã đánh giá `spring.task.scheduling.pool.size` khi SimpleAsyncTaskScheduler được chọn.
- [ ] Đã kiểm tra những job `fixedDelay` cần chạy song song hoặc có nguy cơ chặn scheduler.
- [ ] Đã kiểm tra `@Async` có chạy qua Spring proxy và executor mong muốn.
- [ ] Có admission/concurrency limit mới nếu pool cũ từng là bulkhead.
- [ ] Có DB pool, HTTP pool, rate limit và timeout phù hợp.
- [ ] Không dùng virtual threads như giải pháp tăng CPU-bound throughput.
- [ ] Đã kiểm tra server request execution và event-loop architecture riêng.
- [ ] Đã kiểm tra daemon virtual threads/`spring.main.keep-alive` cho background-only app.
- [ ] Đã kiểm tra pinning và hiệu năng I/O thực tế khi cần.
- [ ] Đã đo startup, throughput, P95/P99, heap, errors, rejected/blocked tasks.
- [ ] Đã chạy load test với downstream constraints giống production.
- [ ] Đã thử shutdown khi có tasks in-flight và xác nhận cleanup.
- [ ] Đã ghi tài liệu rõ vì sao giới hạn mới nằm ở executor/resource cụ thể.

## 28. Tổng kết

1. **Virtual threads không dùng mô hình fixed-size worker pool cho auto-configured task executor/scheduler của Spring Boot 3.3.** Khi bật `spring.threads.virtual.enabled=true` trên Java 21+, Boot chuyển executor sang `SimpleAsyncTaskExecutor` và scheduler sang `SimpleAsyncTaskScheduler` trong các trường hợp auto-config tương ứng.
2. Vì vậy **`spring.task.execution.pool.core-size`, `max-size`, `queue-capacity`, `keep-alive` và `spring.task.scheduling.pool.size` không còn tác dụng với những simple components tự cấu hình**.
3. **`spring.task.execution.simple.concurrency-limit` và `spring.task.scheduling.simple.concurrency-limit`** là những lựa chọn cho giới hạn concurrency tương ứng, nhưng **không tương đương** pool size/queue-capacity cũ và không giới hạn toàn bộ JVM.
4. **Custom platform-thread pools, JDBC/HTTP connection pools, Reactor Netty event loops và downstream rate limits vẫn độc lập.** Global virtual flag không xóa mọi nhu cầu tuning.
5. **Virtual threads phù hợp nhất với nhiều blocking I/O tasks**, không làm CPU hay tài nguyên ngoài trở nên vô hạn. Cần đặt giới hạn theo resource, backpressure, timeout và theo dõi metrics.
6. **SimpleAsyncTaskScheduler có lưu ý riêng cho fixed-delay**, trong khi fixed-rate/cron hợp với mô hình virtual-thread-per-task hơn; đổi loại trigger chỉ sau khi đánh giá nghiệp vụ.
7. **Đo implementation và thread thực thi thật**, không chỉ nhìn file properties. Chuyển đổi thành công là khi hệ thống giữ đúng throughput, latency, error handling và an toàn downstream dưới tải thật.

### Tài liệu chính thức

- [Spring Boot 3.3 — Virtual Threads](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): cách bật, đặc điểm daemon/keep-alive và caveats.
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): lựa chọn `SimpleAsyncTaskExecutor` / `SimpleAsyncTaskScheduler` khi virtual threads được bật.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.task.execution.pool.*`, `spring.task.execution.simple.concurrency-limit`, `spring.task.scheduling.pool.size` và simple scheduler concurrency.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): các implementation executor/scheduler và caveat fixed-delay với `SimpleAsyncTaskScheduler`.
- [Spring Framework 6.1 — SimpleAsyncTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html): scheduler thread, fixed-delay và concurrency limit.
- [Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): mô hình virtual threads, khuyến nghị sử dụng và quan hệ với blocking operations.
