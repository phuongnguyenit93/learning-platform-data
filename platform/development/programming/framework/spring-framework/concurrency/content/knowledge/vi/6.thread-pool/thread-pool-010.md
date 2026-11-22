# Phân biệt giá trị mặc định của Spring Framework với cấu hình do ứng dụng cung cấp

## 1. Câu hỏi cần trả lời

Khi viết một ứng dụng dùng `@Async`, `@Scheduled` hoặc `TaskExecutor`, ta thường nghe những phát biểu như “Spring có sẵn 8 luồng”, “scheduler mặc định chỉ có 1 luồng”, hay “chỉnh `maxPoolSize` lên 50 sẽ chạy 50 tác vụ”. Những phát biểu này chỉ đúng trong **một lớp cấu hình và điều kiện cụ thể**. Cùng tên “Spring” nhưng thực tế có thể đề cập đến:

1. **Spring Framework thuần:** các interface, class thực thi và cơ chế chọn executor/scheduler khi bật annotation.
2. **Giá trị khởi tạo của một class:** ví dụ một `new ThreadPoolTaskExecutor()` có cấu hình ban đầu do chính class đó quy định.
3. **Spring Boot auto-configuration:** Boot quan sát các bean và điều kiện hiện có, có thể tạo thêm executor/scheduler với bộ mặc định **của Boot**.
4. **Thuộc tính cấu hình ứng dụng:** `application.properties`/`application.yml`, biến môi trường, command-line arguments, profile; chỉ ảnh hưởng khi có thành phần thực sự đọc/bind chúng.
5. **Bean hoặc cấu hình tường minh của ứng dụng:** `@Bean`, `AsyncConfigurer`, `SchedulingConfigurer`, `@Async("beanName")` và các setter như `setCorePoolSize`.
6. **Trạng thái thực khi chạy:** số luồng hiện có, số tác vụ active, hàng đợi và số task bị từ chối thay đổi theo tải, khác với các giá trị cấu hình.

Mục tiêu của bài: biết **ai tạo pool**, **ai chọn pool**, **giá trị nào thật sự có hiệu lực**, **cách kiểm chứng** thay vì dựa vào một con số “mặc định Spring” không có ngữ cảnh.

Ví dụ và các giá trị cụ thể được đặt trong phạm vi **Spring Framework 6.1/6.2, Spring Boot 3.3.x với Java 17 (platform threads)**. Khi chuyển sang Java 21 virtual threads, Spring Boot 3.4+, Spring Boot 4 hoặc đổi thành phần tích hợp, phải đối chiếu tài liệu theo đúng phiên bản. Không suy diễn một mặc định là bất biến qua các thế hệ.

## 2. Phân biệt bốn khái niệm dễ nhầm

### 2.1. Abstraction không đồng nghĩa một pool

`org.springframework.core.task.TaskExecutor` mô tả thao tác `execute(Runnable)`. Interface không quy định phải tạo thread mới hay có queue:

- `SyncTaskExecutor`: chạy ngay trên **luồng gọi**; lời gọi chờ task kết thúc.
- `SimpleAsyncTaskExecutor`: mỗi lần thực thi thường tạo thread mới, không phải thread pool tái sử dụng; có thể cấu hình giới hạn đồng thời.
- `ThreadPoolTaskExecutor`: bọc `ThreadPoolExecutor`, có `corePoolSize`, `maxPoolSize`, `queueCapacity` và chính sách từ chối.
- `TaskScheduler` phục vụ lập lịch theo thời điểm/chu kỳ, khác với mục tiêu chỉ “gửi việc” của executor. `ThreadPoolTaskScheduler` có pool dành cho scheduled tasks.

Vì vậy lời gọi `@Async` không chứng minh đang dùng một thread pool. Cần biết **implementation cụ thể** được chọn.

### 2.2. “Mặc định của class” và “mặc định khi auto-config” khác nhau

Ví dụ `new ThreadPoolTaskExecutor()` (được khởi tạo và quản lý vòng đời đúng) có các giá trị ban đầu trong Spring Framework 6.1:

| Thuộc tính | Giá trị mặc định của bản thân class |
| --- | --- |
| `corePoolSize` | 1 |
| `maxPoolSize` | `Integer.MAX_VALUE` |
| `queueCapacity` | `Integer.MAX_VALUE` (hàng đợi gần như không giới hạn) |
| `keepAliveSeconds` | 60 |
| `ThreadPoolTaskScheduler.poolSize` | 1 |

Điểm tinh tế: với queue gần như không giới hạn, khi số tác vụ vượt số core, các task thường được **xếp hàng**; pool gần như không có lý do tăng lên gần `maxPoolSize`. Tăng mỗi `maxPoolSize` mà vẫn giữ queue không giới hạn thường **không tạo thêm nhiều worker theo mong muốn**. Phải thiết kế cùng lúc core/max/queue/rejection dựa trên tải thực tế.

Một `ThreadPoolTaskExecutor` là **class của Spring Framework** nhưng nếu Spring Boot tạo và cấu hình class đó, giá trị thực có thể khác (ví dụ core 8 của Boot 3.3). **Cùng class, không nhất thiết cùng cấu hình.**

### 2.3. Auto-configuration là việc có điều kiện

Spring Framework cung cấp công cụ và fallback khi bật annotation. Spring Boot cung cấp thêm các cấu hình tự động, nhưng chỉ khi **điều kiện auto-configuration phù hợp**. Khi ứng dụng khai báo bean riêng, Boot có thể bỏ qua một phần auto-configuration. Không nên diễn giải “Boot mặc định tạo X” thành “Boot chắc chắn tạo X trong mọi application context”.

### 2.4. Cấu hình mong muốn khác cấu hình thực

Giá trị trong file properties có thể không được áp dụng nếu ứng dụng dùng bean tự tạo bằng `new`/`@Bean` và không bind giá trị từ Boot builder/properties. Vì thế phải kiểm tra **bean thực tế** và các getter sau khi context đã khởi động, đồng thời quan sát metric pool/queue dưới tải.

## 3. Spring Framework thuần: luật chọn mặc định

### 3.1. `@EnableAsync` và `@Async`

Với Spring Framework 6.1/6.2, khi đã bật `@EnableAsync`, nếu không chỉ định executor qua `AsyncConfigurer` hay qualifier cụ thể, cơ chế mặc định tìm:

1. Một bean **`TaskExecutor` duy nhất** trong context.
2. Nếu không chọn được theo cách đó, một bean kiểu `Executor` tên **`taskExecutor`**.
3. Nếu không có ứng viên phù hợp, dùng fallback **`SimpleAsyncTaskExecutor`** cho các lời gọi async.

Đây là quy tắc **lựa chọn khi annotation-driven async hoạt động**, không phải lời hứa rằng Spring Framework thuần tự tạo một `ThreadPoolTaskExecutor` 8 luồng. `SimpleAsyncTaskExecutor` không tái sử dụng worker kiểu pool; cần nghĩ đến chi phí thread và giới hạn đồng thời khi công việc nhiều.

Có thể điều khiển rõ bằng:

~~~java
// Trích đoạn bên trong một Spring-managed service:
@Async("reportExecutor")
public void createReport(String reportId) {
    // Chạy bằng executor bean tên reportExecutor nếu đi qua Spring proxy.
}
~~~

`@Async("reportExecutor")` chỉ rõ bean cần dùng cho phương thức đó; không phải thay đổi mặc định chung cho tất cả phương thức `@Async`. Với `@EnableAsync` mặc định proxy mode, gọi nội bộ `this.createReport(...)` có thể bỏ qua proxy và không kích hoạt interceptor. Muốn đặt mặc định chung theo code, dùng `AsyncConfigurer#getAsyncExecutor()` và quản lý vòng đời executor phù hợp.

**Nhận diện lỗi:** một app có hai `TaskExecutor` bean và không có bean phù hợp tên `taskExecutor` có thể không chọn được “mặc định” như bạn nghĩ. Đặt qualifier tường minh hoặc cấu hình default rõ ràng thay vì dựa vào thứ tự đăng ký bean.

### 3.2. `@EnableScheduling` và `@Scheduled`

Khi bật `@EnableScheduling`, Spring Framework tìm một `TaskScheduler` duy nhất, hoặc bean `TaskScheduler` tên **`taskScheduler`**; nó cũng thử lookup tương ứng với `ScheduledExecutorService`. Nếu không có ứng viên, registrar có thể tạo **scheduler cục bộ một luồng**.

Điều này không có nghĩa Framework mặc định đăng ký một bean `ThreadPoolTaskScheduler` do ứng dụng có thể `getBean(ThreadPoolTaskScheduler.class)` lấy được. Fallback nội bộ của registrar khác với một bean ứng dụng có thể inject hoặc cấu hình bằng Boot properties.

Ví dụ cấp bean tường minh:

~~~java
// Đặt trong class @Configuration.
@Bean("taskScheduler")
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(3);
    scheduler.setThreadNamePrefix("periodic-");
    return scheduler;
}
~~~

Khi Spring quản lý bean, nó lo lifecycle/initialization thích hợp. Nếu tự tạo thủ công ngoài Spring context, cần khởi tạo/đóng executor đúng cách. Với `@Scheduled(fixedDelay = ...)`, lần tiếp theo được tính sau khi lần trước kết thúc; với `fixedRate` và cron, lịch chạy còn phụ thuộc scheduler được chọn và mức tải.

### 3.3. Không bật annotation thì không tự có hành vi annotation

- `@EnableAsync` cho phép Spring intercept lời gọi `@Async` qua cơ chế đã đăng ký.
- `@EnableScheduling` cho phép Spring đăng ký các phương thức `@Scheduled`.
- Khởi động Spring Boot hoặc có bean `TaskExecutor` **không tự đồng nghĩa** mọi phương thức có `@Async`/`@Scheduled` đã được bật. Kiểm tra annotation và application context thực sự đang hoạt động.

## 4. Spring Boot 3.3.x: một tầng mặc định khác

Với Java 17 và virtual threads **không bật**, tài liệu Spring Boot 3.3 mô tả:

| Trường hợp | Mặc định thường gặp khi đủ điều kiện auto-config |
| --- | --- |
| Không có bean `Executor` do ứng dụng cung cấp | Boot có thể tạo `AsyncTaskExecutor` kiểu `ThreadPoolTaskExecutor` |
| `ThreadPoolTaskExecutor` do Boot tự tạo | **8 core threads**; có thể điều chỉnh bằng `spring.task.execution.*` |
| Cần scheduler cho `@Scheduled`, chưa có scheduler do app cung cấp | Boot có thể auto-config `ThreadPoolTaskScheduler` |
| Scheduler Boot kiểu `ThreadPoolTaskScheduler` | **1 scheduler thread** mặc định; điều chỉnh qua `spring.task.scheduling.*` |
| Java 21+ và bật `spring.threads.virtual.enabled=true` | Boot dùng các implementation phù hợp virtual threads, như `SimpleAsyncTaskExecutor` và `SimpleAsyncTaskScheduler`; pooling properties không áp dụng tương đương cho scheduler virtual-thread |

Đặt cạnh Spring Framework thuần:

| Câu hỏi | Spring Framework khi dùng annotation | Spring Boot 3.3 auto-config thông thường |
| --- | --- | --- |
| Ai quyết định executor? | Lookup bean `TaskExecutor` duy nhất, rồi `Executor` tên `taskExecutor`, rồi fallback | Boot có thể **cung cấp bean** auto-config nên lookup của Framework nhìn thấy bean ấy |
| Không có executor khả dụng? | `SimpleAsyncTaskExecutor` fallback cho `@Async` | `ThreadPoolTaskExecutor` auto-config nếu điều kiện phù hợp và không bật virtual threads |
| Số core “mặc định”? | Không có một con số áp dụng cho mọi loại `TaskExecutor`; class `ThreadPoolTaskExecutor` khởi tạo trực tiếp có core 1 | Pool do Boot tạo có core 8 trên platform threads |
| Scheduler mặc định? | Fallback scheduler nội bộ một luồng nếu không tìm được bean | Boot có thể tạo bean `ThreadPoolTaskScheduler`, mặc định pool 1 |
| Cách cấu hình? | `@Bean`, setter, `AsyncConfigurer`, `SchedulingConfigurer`, qualifier | Cũng có các cách Framework, thêm `spring.task.execution.*`/`spring.task.scheduling.*` cho auto-config |

**Không đồng nhất executor và scheduler:** `spring.task.execution.pool.core-size=8` không biến scheduler thành tám luồng. Muốn scheduler pool 3, dùng `spring.task.scheduling.pool.size=3` (khi Boot auto-config scheduler) hoặc setter của bean tương ứng.

### 4.1. Các properties thường dùng

`src/main/resources/application.properties` trong Boot 3.3 (chỉ có tác dụng với auto-config tương ứng):

~~~properties
# Tác vụ bất đồng bộ do Boot quản lý:
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=12
spring.task.execution.pool.queue-capacity=100
spring.task.execution.pool.keep-alive=30s
spring.task.execution.thread-name-prefix=app-worker-

# Tác vụ có lịch do Boot quản lý:
spring.task.scheduling.pool.size=2
spring.task.scheduling.thread-name-prefix=app-schedule-
~~~

Ví dụ này **không phải giá trị default**: đây là **override do ứng dụng cung cấp**. Một số giá trị khi cùng khai báo mới có ý nghĩa kết hợp: `max-size` phát huy tác dụng khi queue hữu hạn bị đầy; khi queue đầy và pool tới max, task có thể bị từ chối tùy rejection policy.

Boot configuration properties có quy tắc precedence: command line/environment có thể ghi đè file cấu hình theo thứ tự nạp của Boot. Trong ứng dụng thực, đừng chỉ đọc file `application.properties` rồi kết luận giá trị đang chạy; hãy kiểm tra resolved `Environment` và bean runtime, đồng thời chú ý active profile.

### 4.2. Khi tự định nghĩa bean, properties có tự áp dụng không?

Giả sử ứng dụng tự khai báo:

~~~java
// Trích đoạn trong @Configuration; không phải class đầy đủ.
@Bean("applicationTaskExecutor")
ThreadPoolTaskExecutor applicationTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(16);
    return executor;
}
~~~

Với bean này, các setter 2/4/16 là cấu hình **của ứng dụng**. Không được kỳ vọng chỉ cần thêm `spring.task.execution.pool.core-size=8` là Boot tự thay giá trị do setter đặt: Boot auto-config thường **back off** khi bean `Executor` tùy chỉnh đã tồn tại, và một bean tạo bằng setter thủ công không tự đọc toàn bộ namespace `spring.task.execution.*`.

Nếu muốn được áp dụng Boot configuration properties khi tạo bean riêng, dùng builder thích hợp của Boot (ví dụ `ThreadPoolTaskExecutorBuilder`, đã được Boot cấu hình theo môi trường) hoặc tự bind properties có chủ đích; kiểm tra builder và API đúng version. Tránh cấu hình đồng thời qua nhiều kênh mà không biết nguồn nào quyết định giá trị cuối.

### 4.3. Hai tên dễ nhầm: `taskExecutor` và `applicationTaskExecutor`

Trong Spring Framework, `taskExecutor` là tên fallback nổi bật cho `@EnableAsync` khi không tìm được một `TaskExecutor` duy nhất. Trong Spring Boot 3.3, executor auto-config thường mang tên **`applicationTaskExecutor`**; các tích hợp như Spring MVC asynchronous request processing yêu cầu một `AsyncTaskExecutor` phù hợp với tên này.

Nếu ứng dụng có nhiều bean `Executor`, việc `@Async` chọn default và việc MVC chọn executor có thể khác nhau. Một bean tên `reportExecutor` không tự trở thành default cho mọi loại async, cũng không bảo đảm MVC sử dụng nó.

Cách giảm mơ hồ:

1. Với background job quan trọng, dùng `@Async("reportExecutor")` hoặc inject `@Qualifier("reportExecutor") TaskExecutor`.
2. Với Spring MVC async, kiểm tra đúng `AsyncTaskExecutor` tên `applicationTaskExecutor` hoặc cấu hình `AsyncSupportConfigurer` cho MVC.
3. Với `@Scheduled`, chọn `taskScheduler` rõ ràng hoặc cấu hình `SchedulingConfigurer`; đó là **scheduler**, không phải executor bất kỳ.
4. Nếu có nhiều context, mỗi context có tập bean và điều kiện annotation riêng; đừng dựa vào bean ở một context khác.

## 5. Ví dụ chạy được: so sánh default Boot và bean custom

Ví dụ này sử dụng **Java 17, Maven, Spring Boot 3.3.13**, không cần web server. Nó in ra **implementation và giá trị của bean thực tế** trong hai lần chạy: (a) Boot tự cấu hình, (b) ứng dụng khai báo pool riêng. Trong ví dụ không bật virtual threads.

Cấu trúc:

~~~text
pool-defaults/
├── pom.xml
└── src/main/java/com/example/pools/
    ├── PoolDefaultsApplication.java
    ├── AuditService.java
    └── CustomPools.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>pool-defaults</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

### 5.2. PoolDefaultsApplication.java

~~~java
package com.example.pools;

import java.util.concurrent.TimeUnit;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class PoolDefaultsApplication {
    public static void main(String[] args) {
        SpringApplication.run(PoolDefaultsApplication.class, args);
    }

    @Bean
    ApplicationRunner auditPools(
            ApplicationContext context, AuditService auditService) {
        return args -> {
            ThreadPoolTaskExecutor executor = context.getBean(
                    "applicationTaskExecutor", ThreadPoolTaskExecutor.class);
            ThreadPoolTaskScheduler scheduler = context.getBean(
                    "taskScheduler", ThreadPoolTaskScheduler.class);

            System.out.println("EXECUTOR_TYPE="
                    + executor.getClass().getSimpleName());
            System.out.println("CORE=" + executor.getCorePoolSize());
            System.out.println("MAX=" + executor.getMaxPoolSize());
            System.out.println("QUEUE_CAPACITY=" + executor.getQueueCapacity());
            System.out.println("SCHEDULER_TYPE="
                    + scheduler.getClass().getSimpleName());
            System.out.println("SCHEDULER_CORE="
                    + scheduler.getScheduledThreadPoolExecutor().getCorePoolSize());

            // Chạy @Async qua bean proxy; tên thread có thể thay đổi.
            String worker = auditService.workerName().get(5, TimeUnit.SECONDS);
            System.out.println("WORKER_THREAD=" + worker);
        };
    }
}
~~~

`getCorePoolSize()`, `getMaxPoolSize()` và `getQueueCapacity()` cho biết cấu hình pool. Chúng **không** cho biết số worker đang active: muốn xem trạng thái hiện tại dùng `getActiveCount()`, `getPoolSize()`, `getQueueSize()` hoặc metric. Với scheduler, đọc `getScheduledThreadPoolExecutor().getCorePoolSize()` để quan sát kích thước core được cấu hình trong `ScheduledThreadPoolExecutor`. Tại startup thường chưa có đủ task để tạo hết số worker; đừng dùng “current pool size” thay cho “configured core size”.

### 5.3. AuditService.java

~~~java
package com.example.pools;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AuditService {
    @Async("applicationTaskExecutor")
    public CompletableFuture<String> workerName() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }
}
~~~

Method `workerName()` được gọi từ bean khác qua proxy và chọn `applicationTaskExecutor` một cách tường minh. Trả `CompletableFuture` cho phép demo đợi kết quả để in ra; trong endpoint xử lý nền thực tế thường không gọi `get()` trên request thread nếu muốn đáp ứng nhanh.

### 5.4. CustomPools.java

~~~java
package com.example.pools;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "demo.custom", havingValue = "true")
public class CustomPools {
    @Bean("applicationTaskExecutor")
    ThreadPoolTaskExecutor appExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(12);
        executor.setThreadNamePrefix("custom-worker-");
        return executor;
    }

    @Bean("taskScheduler")
    ThreadPoolTaskScheduler scheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(3);
        scheduler.setThreadNamePrefix("custom-schedule-");
        return scheduler;
    }
}
~~~

Khi không có `demo.custom=true`, cả hai `@Bean` trên **không được khai báo** do điều kiện ở class. Spring Boot có thể tự tạo executor và scheduler tương ứng. Khi bật flag, bean do ứng dụng khai báo xuất hiện; auto-config thích hợp của Boot nhường quyền, và setter của ứng dụng quyết định giá trị. Mọi số 2, 4, 12, 3 trong `CustomPools` là cấu hình **custom**, không phải default của Framework.

Để chắc chắn Boot nhận ra cần scheduler, demo bật `@EnableScheduling`. Nếu project của bạn không có nhu cầu lập lịch thì có thể bỏ nó và phần scheduler; việc auto-configuration phụ thuộc điều kiện đăng ký của phiên bản Boot.

### 5.5. Chạy hai chế độ

Chạy ở thư mục chứa `pom.xml`, cần JDK 17+ và Maven:

~~~bash
# Chế độ A: dùng auto-configuration Boot khi không có custom bean.
mvn spring-boot:run

# Dừng app trước khi chạy tiếp, ví dụ Ctrl+C.
# Chế độ B: bật hai bean do ứng dụng tự khai báo.
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.custom=true"
~~~

**Chế độ A** (Spring Boot 3.3.13 trên Java 17, không có `Executor` khác; bỏ qua các dòng log framework và hậu tố tên worker biến thiên):

~~~text
EXECUTOR_TYPE=ThreadPoolTaskExecutor
CORE=8
MAX=2147483647
QUEUE_CAPACITY=2147483647
SCHEDULER_TYPE=ThreadPoolTaskScheduler
SCHEDULER_CORE=1
WORKER_THREAD=task-1
~~~

Dòng `WORKER_THREAD=task-1` là **ví dụ về tên luồng**, không phải một chuỗi được bảo đảm nếu cấu hình khác, có thành phần khác sử dụng pool hoặc thay thread factory. Các con số in từ getter là điểm so sánh chính trong môi trường giả định này.

**Chế độ B** (bean custom từ `CustomPools`; tương tự bỏ qua log):

~~~text
EXECUTOR_TYPE=ThreadPoolTaskExecutor
CORE=2
MAX=4
QUEUE_CAPACITY=12
SCHEDULER_TYPE=ThreadPoolTaskScheduler
SCHEDULER_CORE=3
WORKER_THREAD=custom-worker-1
~~~

Giá trị tên thread cuối cũng là ví dụ; prefix `custom-worker-` do ứng dụng đặt. **Cả hai chế độ cùng dùng class `ThreadPoolTaskExecutor` và `ThreadPoolTaskScheduler` nhưng cấu hình khác**. Do đó không thể chỉ nhìn tên class trong log và đoán “mặc định” đã có hiệu lực.

**Giới hạn của demo:** không cấu hình `spring.task.execution.pool.*` trong file properties nên chế độ A cho thấy baseline Boot; nếu bổ sung properties hoặc biến môi trường khác, số liệu sẽ thay đổi. Không có tác vụ `@Scheduled` trong ví dụ; bean scheduler vẫn có thể được Boot tạo do annotation scheduling đã bật, nhưng lịch thực tế cần một method `@Scheduled` để chạy.

### 5.6. Nếu chỉ muốn đổi Boot properties mà không thêm bean

Có thể giữ chế độ A và chạy với argument:

~~~bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--spring.task.execution.pool.core-size=3 --spring.task.execution.pool.max-size=5 --spring.task.execution.pool.queue-capacity=10 --spring.task.scheduling.pool.size=2"
~~~

Khi Boot tự tạo cả hai pool, getter kỳ vọng phản ánh `CORE=3`, `MAX=5`, `QUEUE_CAPACITY=10` và `SCHEDULER_CORE=2`. Thứ tự/phân tích cú pháp command-line arguments ở đây do Spring Boot plugin truyền sang ứng dụng; nếu dùng PowerShell, giữ nguyên cặp dấu ngoặc kép quanh toàn bộ giá trị `-Dspring-boot.run.arguments=...`.

Ngược lại, nếu chạy flag `demo.custom=true` cùng các property trên, `CustomPools` vẫn gán 2/4/12 và 3 bằng setter, bởi nó không dùng Boot builder để đọc các property ấy. Đây là một **thử nghiệm có thể lặp lại** để phân biệt cấu hình do Boot cung cấp với cấu hình do ứng dụng tự khai báo.

## 6. Vì sao max-size có thể không phát huy tác dụng?

Dù số cấu hình đã xác định, hoạt động của `ThreadPoolTaskExecutor` còn phụ thuộc thuật toán `ThreadPoolExecutor` phía dưới.

Với core=2, max=4, queueCapacity=12:

1. Khi hai worker đang bận, task mới có thể đi vào queue.
2. Khi queue đạt giới hạn và pool chưa đạt max, executor có thể mở thêm worker.
3. Khi pool đã đạt max và queue đầy, task mới có thể bị từ chối (`TaskRejectedException` khi gọi qua Spring `TaskExecutor`); cần chính sách backpressure và trả HTTP 429/503 khi phù hợp.
4. Task chờ trong queue tăng latency; tăng queue quá lớn có thể che giấu quá tải, làm request đợi lâu trước khi được xử lý.

Với queue không giới hạn như giá trị ban đầu của `ThreadPoolTaskExecutor`, pool chủ yếu giữ ở mức core, dù max đặt rất lớn. Do đó một nhận định kiểu “max=100 thì chạy được 100 job song song” thường sai nếu không xem queue. Mặt khác, một pool lớn cũng không bảo đảm throughput nếu giới hạn thật nằm ở connection pool, DB hoặc API bên ngoài.

Trong ứng dụng thực, nên chọn pool theo đặc điểm công việc: CPU-bound không nên nhân bản vô hạn số worker; I/O-bound có thể cần thêm độ đồng thời nhưng phải tuân giới hạn tài nguyên và timeout. Chia pool cho nhiệm vụ dài/chậm và nhiệm vụ nhanh có SLA khác nhau để tránh chúng chiếm hết hàng đợi của nhau.

## 7. Java 21 và virtual threads thay đổi cách hiểu “default”

Spring Boot 3.3 có hỗ trợ bật virtual threads với Java 21+ bằng `spring.threads.virtual.enabled=true`. Khi đó Boot có thể tự cấu hình:

- `SimpleAsyncTaskExecutor` sử dụng virtual threads thay vì `ThreadPoolTaskExecutor` thông thường;
- `SimpleAsyncTaskScheduler` thay vì scheduler pool platform threads truyền thống.

Vì thế `spring.task.execution.pool.core-size` hay `spring.task.scheduling.pool.size` **không thể được diễn giải như số lượng virtual threads tối đa**. Với `SimpleAsyncTaskScheduler`, fixed-delay tasks có quy tắc đặc biệt liên quan đến một scheduler thread; phải đọc hướng dẫn theo implementation.

Virtual threads không miễn trừ giới hạn DB connections, sockets, API quota hoặc CPU; cần semaphore/rate limit và quan sát thực tế khi tải cao. Chỉ vì Java 21 có virtual threads không có nghĩa mọi custom `ThreadPoolTaskExecutor` tự biến thành virtual-thread executor: điều kiện và kiểu bean vẫn quan trọng.

## 8. Cách xác định cấu hình thật trong một hệ thống đang chạy

Có thể kiểm tra theo chuỗi sau:

1. **Chốt phiên bản:** Spring Framework, Spring Boot và Java đang chạy; có bật virtual threads không?
2. **Kiểm tra chức năng được bật:** có `@EnableAsync`, `@EnableScheduling` và method annotation tương ứng trong context không?
3. **Liệt kê beans:** các bean `Executor`, `TaskExecutor`, `AsyncTaskExecutor`, `TaskScheduler` và `ScheduledExecutorService`; chú ý tên, kiểu và số lượng.
4. **Xác nhận luật chọn:** `@Async("name")` có qualifier? Có `AsyncConfigurer` không? Scheduled registrar được `SchedulingConfigurer` trỏ tới đâu? Có trùng tên `taskExecutor`/`applicationTaskExecutor`/`taskScheduler` không?
5. **Đọc nguồn cấu hình:** resolved `Environment`, active profiles, command-line, YAML/properties; xem bean được Boot auto-config tạo hay code ứng dụng tự tạo.
6. **Đọc runtime:** getter cấu hình core/max/queue/pool size, active thread count, current pool size, queue length và rejection metrics; có thể xuất qua Micrometer/Actuator nếu dự án đã trang bị.
7. **Thử tải và shutdown:** đo thời gian chờ, task rejection, context propagation, timeout và cách dừng có chờ các job đang chạy hay không.

Trích đoạn Java để liệt kê executor và scheduler từ `ApplicationContext` (đặt trong runner/debug utility được phép; đây là snippet, không phải chương trình độc lập):

~~~java
String[] executors = context.getBeanNamesForType(
        java.util.concurrent.Executor.class);
String[] schedulers = context.getBeanNamesForType(
        org.springframework.scheduling.TaskScheduler.class);

System.out.println("Executor beans = " + java.util.Arrays.toString(executors));
System.out.println("Scheduler beans = " + java.util.Arrays.toString(schedulers));
~~~

Tên bean và số lượng trong danh sách tùy toàn bộ application context. Đây là cách xác minh sự tồn tại, **chưa đủ** để kết luận annotation chọn bean nào; đối chiếu thêm luật lookup và qualifier. Việc tự ý lấy một bean bằng kiểu chung khi có nhiều bean có thể gây `NoUniqueBeanDefinitionException`; muốn chắc chắn hãy dùng tên + kiểu hoặc `@Qualifier`.

### Mẫu ghi quyết định cấu hình khi review code

| Mục cần review | Giá trị cần ghi nhận |
| --- | --- |
| Framework / Boot / JDK | Chính xác phiên bản đang deploy |
| Công việc | `@Async` nào, `@Scheduled` nào, MVC async hay job do code gọi `execute` |
| Executor được chọn | Tên và class thực tế, nguồn tạo bean |
| Thread pool | core, max, queue, keepAlive, rejection policy |
| Scheduler | tên/kiểu bean, số luồng, cron/fixedDelay/fixedRate và múi giờ |
| Nguồn override | code setter, Boot properties, biến môi trường, profile, builder |
| Vận hành | active/queued/rejected, SLA, shutdown, retry, idempotency |

Dùng bảng này giúp review được vì sao hai môi trường “đều là Spring Boot” lại có số luồng và hiệu năng khác nhau.

## 9. Các lỗi phổ biến

| Hiểu nhầm / hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| “Spring Framework mặc định có 8 worker” | 8 core là baseline của **Boot 3.3 auto-config platform-thread executor**, không phải mọi `TaskExecutor` | Xác định ai tạo bean và runtime type |
| “Tự `new ThreadPoolTaskExecutor` mặc định giống Boot” | Class direct default core=1, Boot builder có thể đặt core=8 | In getter, đặt setter rõ |
| “Đã đặt `max-size=20`, phải chạy 20 task” | Queue không giới hạn có thể giữ pool ở core | Thiết kế queue hữu hạn, kiểm thử saturation |
| “Sửa `application.properties` nhưng pool không đổi” | Bean custom không dùng Boot binding/builder; hoặc cấu hình bị nguồn khác override | Kiểm tra bean source và resolved environment |
| “`@Async` không chạy nền” | Chưa bật async, self-invocation, hoặc chọn `SyncTaskExecutor` | Kiểm tra `@EnableAsync`, proxy và tên luồng |
| “`@Scheduled` chạy song song khi tăng execution core” | Executor pool và scheduler pool khác loại | Cấu hình `spring.task.scheduling.pool.size` hoặc custom scheduler |
| “Đặt tên `reportExecutor` thì MVC cũng dùng” | MVC có yêu cầu riêng về `AsyncTaskExecutor`/`applicationTaskExecutor` | Cấu hình MVC async rõ ràng |
| “Mọi `@Async` dùng bean tôi vừa khai báo” | Nhiều bean, qualifier hoặc `AsyncConfigurer` quyết định chọn | Chỉ rõ `@Async("beanName")` và audit |
| “Một scheduler là đủ cho toàn cluster” | Mỗi application context/pod có scheduler riêng | Lock phân tán, idempotency, hoặc scheduler chuyên dụng |
| “Virtual threads vẫn có pool-size 8” | Auto-config có thể chọn implementation khác | Xem class thật và giới hạn external resources |

Một số lỗi chỉ xuất hiện khi deploy nhiều instance hoặc nhận tải lớn. Khởi động thành công và một request chạy đúng **không chứng minh** đã lựa chọn pool tối ưu.

## 10. Bài tập tự kiểm tra

1. Trên Spring Framework thuần, có `@EnableAsync` nhưng không có `TaskExecutor` duy nhất hay bean `Executor` tên `taskExecutor`. Spring dùng fallback nào? Có tái sử dụng worker kiểu pool không?
2. `new ThreadPoolTaskExecutor()` và `ThreadPoolTaskExecutor` do Spring Boot 3.3 tự tạo có cùng giá trị core mặc định không? Tại sao?
3. Boot tự cấu hình executor core=8, nhưng bạn thêm `@Bean("applicationTaskExecutor")` đặt core=2. Đâu là nguồn quyết định giá trị core thực tế?
4. Ứng dụng có hai `TaskExecutor`: `imageExecutor` và `reportExecutor`. `@Async` không qualifier nên chọn cái nào? Cần thay đổi gì để hành vi xác định?
5. Tại sao tăng `spring.task.execution.pool.max-size` mà để queue vô hạn có thể không tăng độ đồng thời?
6. `@Scheduled` dùng pool nào, và vì sao đổi cấu hình async executor chưa chắc làm job cron chạy song song?
7. Sau khi bật Java 21 virtual threads, tại sao phải kiểm tra class của executor/scheduler trước khi diễn giải `core-size` và `pool.size`?
8. Nếu hai pod chạy cùng cron lúc nửa đêm, việc tăng pool size hay đổi tên bean có ngăn dữ liệu cập nhật hai lần không? Cần cơ chế điều phối gì?

**Kết luận sử dụng:** khi nói “mặc định của Spring”, luôn hỏi rõ **phiên bản, class, nơi tạo bean, luật chọn executor và nguồn cấu hình thực sự có hiệu lực**. Chỉ sau khi trả lời các câu ấy mới hợp lý để nói pool có bao nhiêu luồng hoặc ứng dụng nên chỉnh property nào.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — @EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework 6.2 — @EnableScheduling Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/EnableScheduling.html)
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html)