# Phân biệt cấu hình Spring Framework với tự động cấu hình Spring Boot

## 1. Mục tiêu và phạm vi

Trong Spring, bạn có thể viết `@Configuration` và `@Bean` để tạo một `ThreadPoolTaskExecutor` hoặc `ThreadPoolTaskScheduler`. Khi dùng Spring Boot, ứng dụng đôi khi đã có các bean tương tự dù bạn không hề viết cấu hình Java. Hai hiện tượng này dễ khiến người học kết luận sai rằng “Spring Framework tự tạo thread pool”, rằng “thêm `@Async` là Boot đã tự bật async”, hoặc rằng “đổi `spring.task.execution.pool.*` luôn sửa được mọi executor”.

Bài này phân biệt **hai lớp trách nhiệm**:

1. **Spring Framework** cung cấp IoC container, cấu hình bean, các abstraction `TaskExecutor`/`TaskScheduler`, các implementation, proxy xử lý `@Async` và cơ chế đăng ký `@Scheduled`. Bạn có thể khai báo chúng trong ứng dụng Spring thuần mà không cần Spring Boot.
2. **Spring Boot** đứng trên Spring Framework, cung cấp dependency management, khởi tạo ứng dụng, **auto-configuration có điều kiện**, cấu hình ngoài qua properties/YAML và những mặc định thuận tiện. Khi điều kiện phù hợp, Boot tạo bean executor/scheduler thay bạn; khi có bean do người dùng tạo, kết quả có thể khác.

Nội dung tập trung vào **cấu hình tài nguyên thực thi** trong chủ đề concurrency: executor, scheduler, lựa chọn bean, thread pool, tính hiệu lực của properties, lifecycle và cách xác minh. Người học cần biết cách truy ra: **bean nào tồn tại, do ai tạo, ai sử dụng, cấu hình nào đang có hiệu lực và ai đóng tài nguyên**.

Ví dụ mã Java sử dụng Java 17+ với Spring Framework 6.1 / Spring Boot 3.3 làm mốc có thể kiểm chứng; phần virtual threads yêu cầu Java 21+. Nguyên tắc áp dụng rộng hơn, còn default và điều kiện auto-configuration phải đối chiếu phiên bản thực tế.

## 2. Hiểu đúng các tầng

```text
                MÃ NGHIỆP VỤ
    @Async service, @Scheduled task, caller
                       |
            Chọn executor/scheduler
                       |
        +--------------+--------------+
        |                             |
  Spring Framework              Spring Boot
  - @Configuration              - @SpringBootApplication
  - @Bean                       - @EnableAutoConfiguration
  - @EnableAsync                - AutoConfiguration conditions
  - @EnableScheduling           - @ConfigurationProperties
  - TaskExecutor API            - spring.task.execution.*
  - TaskScheduler API           - spring.task.scheduling.*
  - ThreadPoolTaskExecutor      - Default bean nếu đủ điều kiện
  - ThreadPoolTaskScheduler
        |                             |
        +--------------+--------------+
                       |
                Java / JVM / OS
         ThreadPoolExecutor / virtual threads
```

**Mấu chốt:** Boot **sử dụng** các thành phần của Framework và thêm logic cấu hình tự động. Boot không thay đổi bản chất của `ThreadPoolTaskExecutor` hay Java Memory Model. Framework không cần Boot để chạy task; Boot không thể làm cho shared mutable state tự trở nên thread-safe.

### 2.1. Bảng so sánh

| Góc nhìn | Spring Framework thuần | Spring Boot |
| --- | --- | --- |
| Mục tiêu | Hạ tầng DI, bean lifecycle, AOP, task execution/scheduling SPI | Khởi động nhanh, thiết lập thành phần theo classpath và cấu hình |
| Nơi khai báo tài nguyên | Thường `@Configuration`/`@Bean`, XML, bean definitions | Bean thủ công **hoặc** auto-configured bean |
| Cách bật annotation async | `@EnableAsync` hoặc cấu hình XML tương ứng | Vẫn cần `@EnableAsync` khi dùng cơ chế annotation đó |
| Cách bật scheduling | `@EnableScheduling` hoặc XML tương ứng | Vẫn cần cơ chế enable scheduling, thường `@EnableScheduling` |
| Cách chọn executor | `@Async("beanName")`, `AsyncConfigurer`, lookup mặc định | Cùng quy tắc Framework, thêm executor tự cấu hình và một số tích hợp Boot |
| Chỉnh pool | Gọi setter khi tạo bean hoặc dùng properties do ứng dụng tự bind | Có `spring.task.execution.*` cho auto-configured executor phù hợp |
| Chỉnh scheduler | Tạo bean scheduler hoặc qua `SchedulingConfigurer` | Có `spring.task.scheduling.*` khi auto-configured scheduler phù hợp |
| Điều kiện tự tạo bean | Không có cơ chế Boot auto-config mặc định | Classpath + điều kiện bean hiện có + settings + phiên bản |
| Vòng đời | Bean do container tạo thường được container quản lý; tự tạo ngoài container thì tự đóng | Container vẫn quản lý bean, Boot hỗ trợ wiring/config các bean được auto-configure |
| Kiểm chứng | Đọc config, liệt kê beans và quan sát thread/executor | Tương tự, bổ sung condition evaluation và Actuator khi có |

Điều quan trọng là phân biệt bốn việc **khác nhau**: (1) tạo bean executor, (2) bật cơ chế xử lý annotation, (3) chọn executor thực sự của lời gọi và (4) cấu hình tài nguyên của executor đó. Làm được một việc không tự động chứng minh ba việc còn lại.

## 3. Spring Framework thuần: bạn khai báo bean có chủ đích

Trong ứng dụng chỉ dùng Spring Framework, `@Configuration` và `@Bean` là cách trực tiếp khai báo tài nguyên. Framework thực hiện dependency injection, bean initialization/destroy và proxy theo annotation đã được bật. Nó không tự đọc namespace `spring.task.execution.pool.*` của Spring Boot.

### 3.1. Tạo một pool và gắn rõ vào `@Async`

Ví dụ hoàn chỉnh có thể chạy bằng **Java 17 + Maven** và **Spring Framework 6.1.x**, không sử dụng Spring Boot.

Cấu trúc:

```text
framework-only/
├── pom.xml
└── src/main/java/demo/FrameworkOnlyDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>framework-only</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
    </dependencies>
</project>
```

Tệp `src/main/java/demo/FrameworkOnlyDemo.java`:

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class FrameworkOnlyDemo {
    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {
        @Bean("manualExecutor")
        ThreadPoolTaskExecutor manualExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setThreadNamePrefix("manual-");
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(10);
            return executor;
        }

        @Bean
        Worker worker() {
            return new Worker();
        }
    }

    public static class Worker {
        @Async("manualExecutor")
        public CompletableFuture<Boolean> checkExecutor() {
            boolean selected =
                    Thread.currentThread().getName().startsWith("manual-");
            return CompletableFuture.completedFuture(selected);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            Worker worker = context.getBean(Worker.class);
            boolean selected = worker.checkExecutor()
                    .get(5, TimeUnit.SECONDS);
            System.out.println("manual-executor=" + selected);
        }
    }
}
```

Chạy ở thư mục chứa POM:

```bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.FrameworkOnlyDemo
```

Dòng output của chương trình (Maven có thể có thông báo riêng tùy môi trường):

```text
manual-executor=true
```

**Vì sao đúng:** `@EnableAsync` đăng ký hạ tầng xử lý `@Async`; method được gọi qua Spring-managed bean nên proxy có cơ hội intercept; `@Async("manualExecutor")` chỉ rõ bean executor; task kiểm tra prefix từ thread thực thi. `try-with-resources` đóng application context, qua đó Spring xử lý lifecycle bean `ThreadPoolTaskExecutor`.

Không thấy `SpringApplication.run`, `@SpringBootApplication` hay property `spring.task.execution.*` trong ví dụ; vì đây là **Spring Framework thuần**. Bạn có thể thay tên và thông số executor hoàn toàn qua cấu hình bean.

### 3.2. Nếu Framework không có executor bạn tự tạo?

Khi `@EnableAsync` được dùng mà không cấu hình executor riêng, cơ chế async của Framework có quy tắc tìm một `TaskExecutor` phù hợp (hoặc `Executor` mang tên quy ước `taskExecutor`) và có fallback như `SimpleAsyncTaskExecutor`. Fallback này **không phải một pool bounded được Boot cấu hình**, và không có nghĩa một tài nguyên phù hợp tải đã được tạo.

Vì vậy, “code chạy được” chỉ xác nhận lời gọi đã thực thi; chưa chứng minh số worker, queue, giới hạn tải hoặc shutdown phù hợp. Với ứng dụng sản xuất, hãy chỉ định executor và kiểm tra hành vi quá tải.

### 3.3. Không quên phần scheduler

Framework cung cấp `TaskScheduler`, `ThreadPoolTaskScheduler` và `@EnableScheduling`. Bạn có thể khai báo thủ công:

```java
@Configuration
@EnableScheduling
class FrameworkSchedulingConfig {
    @Bean("maintenanceScheduler")
    ThreadPoolTaskScheduler maintenanceScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("manual-schedule-");
        return scheduler;
    }
}
```

Đây là **fragment** trong một dự án Spring có import tương ứng, không phải file Java tự chạy độc lập. Không nhầm `@EnableScheduling` (kích hoạt xử lý annotation) với bean scheduler (cung cấp tài nguyên). Nếu có nhiều scheduler, cần xem cách Spring chọn mặc định hoặc cấu hình rõ theo `SchedulingConfigurer`; đặt một tên bean bất kỳ không chứng minh mọi `@Scheduled` dùng bean đó.

## 4. Spring Boot: bean được tạo bởi auto-configuration có điều kiện

`@SpringBootApplication` bao gồm cơ chế auto-configuration của Boot (qua `@EnableAutoConfiguration`) cùng cấu hình/scan phù hợp. Boot đọc classpath, các bean đã có và giá trị configuration properties, rồi đánh giá nhiều điều kiện như `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty`.

**Auto-configuration có điều kiện** nghĩa là Boot thường tự tạo tài nguyên **khi thiếu những bean tương ứng và điều kiện được thỏa**. Nó không bảo đảm luôn có cùng loại bean trong mọi ứng dụng Boot. Việc bạn thêm một bean executor tùy chỉnh có thể khiến auto-configuration của executor mặc định **back off** (không tạo bean đó). Điều kiện chính xác thay đổi theo phiên bản Boot và loại bean.

Với **Spring Boot 3.3.x**, trong ngữ cảnh không có `Executor` tùy chỉnh:

- Boot có thể auto-configure một `AsyncTaskExecutor`. Khi không bật virtual threads, implementation mặc định là `ThreadPoolTaskExecutor`.
- Khi dùng Java 21+ và bật `spring.threads.virtual.enabled=true`, executor tự cấu hình có thể là `SimpleAsyncTaskExecutor` dùng virtual threads.
- Tích hợp async của Spring, Spring MVC async request và những thành phần khác có quy tắc sử dụng bean auto-configured khác nhau; tên bean và kiểu bean quan trọng.
- Khi cần scheduled execution với `@EnableScheduling`, Boot có thể auto-configure scheduler; với platform threads thường là `ThreadPoolTaskScheduler`, với virtual threads có thể là `SimpleAsyncTaskScheduler`.
- Boot cung cấp properties `spring.task.execution.*` và `spring.task.scheduling.*` để chỉnh **các tài nguyên do Boot tự cấu hình**, theo điều kiện tương ứng.

Những điều trên được mô tả trong tài liệu chính thức Spring Boot 3.3.x; với Boot 4.x hoặc release khác phải mở đúng version reference.

### 4.1. Ví dụ Boot: chỉ cấu hình qua application.yml

Giả định một dự án **Spring Boot 3.3.x**, có `spring-boot-starter`, dùng Java 17+, chưa khai báo bean `Executor` hay `AsyncConfigurer` tùy chỉnh, và không bật virtual threads.

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  main:
    web-application-type: none
  threads:
    virtual:
      enabled: false
  task:
    execution:
      thread-name-prefix: boot-work-
      pool:
        core-size: 2
        max-size: 4
        queue-capacity: 20
        keep-alive: 30s
    scheduling:
      thread-name-prefix: boot-schedule-
      pool:
        size: 2
```

Dự án không cần có class `@Configuration` nào tự tạo `ThreadPoolTaskExecutor` để Boot có thể cấu hình executor theo các thuộc tính trên. Nhưng **để annotation `@Async` được xử lý** vẫn cần `@EnableAsync`; và để xử lý `@Scheduled` thông thường cần `@EnableScheduling`.

Tệp `src/main/java/demo/BootAutoExecutorDemo.java`:

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class BootAutoExecutorDemo {
    @Bean
    Worker worker() {
        return new Worker();
    }

    public static class Worker {
        @Async("applicationTaskExecutor")
        public CompletableFuture<Boolean> checkExecutor() {
            boolean selected =
                    Thread.currentThread().getName().startsWith("boot-work-");
            return CompletableFuture.completedFuture(selected);
        }
    }

    public static void main(String[] args) throws Exception {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(BootAutoExecutorDemo.class, args)) {
            AsyncTaskExecutor executor =
                    context.getBean("applicationTaskExecutor",
                                    AsyncTaskExecutor.class);
            boolean selected = context.getBean(Worker.class)
                    .checkExecutor().get(5, TimeUnit.SECONDS);

            System.out.println("bean-type=" +
                    executor.getClass().getSimpleName());
            System.out.println("boot-executor=" + selected);
        }
    }
}
```

Chạy trong dự án Boot đã cấu hình Gradle wrapper và đúng Java:

```bash
./gradlew bootRun
```

Hai dòng ứng dụng kỳ vọng trên **Boot 3.3.x với đúng điều kiện nêu trên**, ngoài log startup:

```text
bean-type=ThreadPoolTaskExecutor
boot-executor=true
```

Boot tạo bean `applicationTaskExecutor` khi thỏa điều kiện; `@Async("applicationTaskExecutor")` chọn nó một cách minh bạch; prefix `boot-work-` đến từ `application.yml`. Việc lấy bean theo tên và kiểu đồng thời tránh tình trạng “có task chạy rồi nên nghĩ là thuộc đúng pool”.

Nếu bật virtual threads, thêm bean executor thủ công, thay phiên bản Boot hoặc thiếu starter phù hợp thì loại bean và output có thể khác. Ví dụ được ràng buộc điều kiện rõ ràng để tránh xem một tình huống là mặc định bất biến.

### 4.2. Chỉ thêm properties không tự bật xử lý annotation

Ba cấu hình có vai trò khác nhau:

| Thứ bạn thêm | Điều nó làm | Điều nó không tự làm |
| --- | --- | --- |
| `@EnableAsync` | Bật cơ chế chặn lời gọi qua Spring proxy cho `@Async` | Không tự bảo đảm tạo một bounded pool đáp ứng tải |
| `spring.task.execution.pool.max-size=...` | Chỉnh một property của Boot-managed pool khi property được áp dụng | Không tự đăng ký `@Async` hoặc thay đổi bean tùy chỉnh không bind property |
| `@Async("someExecutor")` | Chỉ định executor cho một method khi advice thực sự chạy | Không tự tạo bean tên `someExecutor` |
| `@EnableScheduling` | Bật xử lý annotation `@Scheduled` | Không biến cron thành job bền vững |
| `spring.task.scheduling.pool.size=...` | Tinh chỉnh Boot-managed thread pool scheduler khi có hiệu lực | Không nhất thiết tác động lên scheduler do code tự tạo |
| `@Bean ThreadPoolTaskExecutor` | Đưa resource tùy chỉnh vào container | Không có nghĩa Boot sẽ áp dụng mọi `spring.task.execution.*` cho bean đó |

Lời gọi nội bộ `this.doAsync()` trong cùng bean thường đi vòng qua proxy `@Async` mặc định. Dù Boot đã tạo `applicationTaskExecutor` đúng cách, self-invocation vẫn có thể làm method chạy trên caller thread. Đây là vấn đề cơ chế proxy của Framework, **không phải lỗi Boot auto-configuration**.

## 5. Khi bạn tự khai báo Executor trong Spring Boot thì sao?

Spring Boot tôn trọng khả năng tùy chỉnh của ứng dụng. Khi một `Executor` đã được khai báo, auto-configuration có thể ngừng tạo executor mặc định; đồng thời cách các integration chọn executor vẫn có yêu cầu tên và kiểu riêng. Đây là nguyên nhân thường gặp nhất của câu “tôi chỉnh YAML nhưng số thread không đổi”.

### 5.1. Mẫu bean tùy chỉnh

Trong ứng dụng Spring Boot, cấu hình sau tạo `ThreadPoolTaskExecutor` do **bạn** chịu trách nhiệm về các thông số:

```java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class CustomExecutionConfig {
    @Bean("domainExecutor")
    ThreadPoolTaskExecutor domainExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(3);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(30);
        executor.setThreadNamePrefix("domain-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

Đây là **fragment Spring**, đặt trong project có dependencies. Nếu method có `@Async("domainExecutor")` và được gọi qua Spring proxy, nó sẽ dùng bean này. Thay `spring.task.execution.pool.core-size` trong YAML **không tự động thay** giá trị 3 được đặt bằng setter trong mã trên.

Có thể đưa các tham số vào `@ConfigurationProperties` riêng, hoặc dùng builder do Boot cung cấp (ví dụ `ThreadPoolTaskExecutorBuilder` ở các phiên bản tương ứng) để tận dụng các customizer/thiết lập, nhưng hãy kiểm tra rõ thuộc tính nào đã bind. Tự tạo bean bằng `new` không đồng nghĩa với việc Boot tự bind mọi property cho nó.

### 5.2. Phân biệt bean `taskExecutor` và `applicationTaskExecutor`

Đây là điểm dễ gây nhầm giữa **method async thông thường** và **các integration**:

- Framework xử lý `@Async`: có thể tìm executor mặc định theo `AsyncConfigurer`, bean `TaskExecutor` phù hợp hoặc tên quy ước `taskExecutor`; `@Async("beanName")` là cách chỉ rõ từng method.
- Theo tài liệu **Spring Boot 3.3**, khi có nhiều bean `Executor`, cơ chế async thông thường có thể fallback theo tên `taskExecutor`.
- Với Spring MVC async request và Spring WebFlux blocking execution support trên Boot 3.3, integration mong đợi `AsyncTaskExecutor` phù hợp có tên `applicationTaskExecutor`.
- `ThreadPoolTaskExecutor` là `AsyncTaskExecutor`, nhưng `java.util.concurrent.ExecutorService` đơn thuần không tự đáp ứng mọi yêu cầu của Spring MVC async integration.
- Hai bean khác nhau có thể cùng tồn tại cho các mục tiêu khác nhau; việc bean “được dùng cho `@Async`” không chứng minh nó cũng xử lý `Callable`/`WebAsyncTask` của MVC.

Bảng tình huống trên Boot 3.3.x:

| Bối cảnh | Điều cần kiểm chứng |
| --- | --- |
| Không khai báo `Executor`, dùng Boot auto-config | `applicationTaskExecutor` tồn tại, loại bean và prefix/size đúng |
| Có một bean `Executor` tự khai báo | Boot có back off không? `@Async` chọn bean nào? MVC còn executor hợp lệ không? |
| Có nhiều bean `Executor` | `AsyncConfigurer`, bean tên `taskExecutor` và `@Async("...")` giải quyết lựa chọn nào? |
| Muốn MVC async dùng bean tùy chỉnh | Có `AsyncTaskExecutor` đúng tên `applicationTaskExecutor` hoặc cấu hình MVC riêng không? |
| Muốn pool riêng cho tác vụ nghiệp vụ | Dùng `@Async("domainExecutor")` và inject bean theo `@Qualifier` |
| Có virtual threads | Bean auto-configured thuộc loại nào? Property pool-size còn có hiệu lực không? |

**Không nên** đổi tên một bean bừa bãi chỉ để làm ứng dụng khởi động được. Tên là một phần hợp đồng wiring cho nhiều integration; thay tên có thể khiến một thành phần dùng pool khác.

### 5.3. Nếu muốn giữ mặc định Boot cho MVC và pool riêng cho domain

Một thiết kế chủ động thường là:

- Cho Spring MVC async dùng bean `applicationTaskExecutor` thuộc kiểu `AsyncTaskExecutor`.
- Cho method nghiệp vụ nặng dùng `@Async("domainExecutor")`.
- Khai báo rõ bean nào phục vụ nhiệm vụ nào, sử dụng `AsyncConfigurer` nếu cần chọn mặc định cho `@Async`.
- Kiểm tra điều kiện auto-configuration với đúng phiên bản Boot: thêm `domainExecutor` có thể khiến Boot **không còn tạo** `applicationTaskExecutor` tự động. Khi đó phải khai báo bean MVC riêng hoặc dùng cơ chế cấu hình được Boot hỗ trợ.
- Đặt queue, rejection, timeout, metrics và shutdown riêng theo loại tải.

Không giả định “Boot luôn bổ sung pool còn thiếu” nếu đã có executor tùy chỉnh. Kiểm chứng danh sách bean thật từ application context sau khi khởi động.

## 6. Ví dụ thực tế: sửa một lỗi cấu hình không có hiệu lực

Giả sử ứng dụng Boot đang có đoạn:

```yaml
spring:
  task:
    execution:
      pool:
        core-size: 8
        max-size: 16
        queue-capacity: 100
```

Nhưng trong source lại có:

```java
@Bean("fileExecutor")
ThreadPoolTaskExecutor fileExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(1000);
    return executor;
}
```

Và method xử lý file:

```java
@Async("fileExecutor")
public CompletableFuture<String> processFile(String name) {
    return CompletableFuture.completedFuture(name);
}
```

Các fragment trên cần imports/project phù hợp. Nếu lời gọi chạy qua proxy, executor dùng là `fileExecutor` với core/max **2**, queue **1000** theo cấu hình Java; sửa YAML của Boot-managed executor không tự thay các setter đã áp dụng lên bean `fileExecutor`.

**Quy trình sửa:**

1. Xác định `@Async("fileExecutor")` đang chỉ đúng bean nào; bảo đảm lời gọi qua proxy.
2. Quyết định một nguồn cấu hình: Java setter, custom `@ConfigurationProperties` được bind vào bean, hay builder/tích hợp Boot được kiểm chứng.
3. Chỉnh giá trị tại nguồn thực sự dùng cho `fileExecutor`, không đổi một property không được tham chiếu.
4. Xác minh `getCorePoolSize()`, `getMaxPoolSize()`, queue capacity và thread prefix trên **bean đã chạy task**.
5. Load test để kiểm tra hành vi queue → tăng worker → rejection; không chỉ so sánh thông số cấu hình.

Nếu thêm một `Executor` khiến auto-config của Boot back off và một integration khác mất bean `applicationTaskExecutor`, phải giải quyết wiring của integration ấy nữa. Đây là tác động kiến trúc cần phát hiện, không chỉ vấn đề cỡ pool.

## 7. Điều kiện auto-configuration hoạt động như thế nào?

Một auto-configuration thường diễn tả quyết định có điều kiện, ví dụ về mặt **khái niệm**:

```text
Nếu có các class/feature liên quan trên classpath
  và chế độ thực thi phù hợp
  và chưa có bean người dùng thuộc điều kiện loại trừ
thì tạo executor/scheduler mặc định
ngược lại, bỏ qua việc tạo mặc định.
```

Đây là mô hình tư duy, **không phải mã điều kiện chính xác** của một release Boot cụ thể. Các annotation như `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty` được dùng trong cơ chế auto-configuration; tên class condition, tên bean và kiểu bean cần đọc trong phiên bản hiện hành.

### 7.1. Thứ tự và thời điểm điều kiện được đánh giá

- Auto-configuration được Boot nhập vào application context, không phải được bạn gọi như hàm thủ công.
- Điều kiện đánh giá dựa trên bean definitions, classpath, environment và cấu hình đã có tại thời điểm thích hợp.
- Nếu một bean tùy chỉnh thỏa điều kiện loại trừ, auto-config sẽ không tạo bản mặc định của Boot; đó là hành vi thiết kế để ứng dụng nắm quyền kiểm soát.
- Nếu source có `@Bean` nhưng class không nằm trong phạm vi scan/import, bean có thể **không tồn tại** ở context bạn đang kiểm tra.
- Nếu một method có `@Async` nhưng không bật async processing hoặc gọi qua đối tượng tự `new`, annotation có thể không tạo lời gọi async.
- Một `@Configuration` của Framework có thể hoạt động cả trong Boot, vì Boot dùng cùng container; chỉ khác ở việc Boot thêm các auto-configurations.

### 7.2. Cách xem nguyên nhân bean được tạo hoặc không tạo

Trong Boot, có thể:

1. Khởi động với debug condition evaluation (ví dụ cờ `--debug` theo phiên bản hỗ trợ) và xem condition evaluation report.
2. Nếu có Actuator, kiểm tra endpoint conditions và beans khi được bật/cho phép, ví dụ `/actuator/conditions`, `/actuator/beans`. Tránh mở những endpoint nhạy cảm công khai.
3. Kiểm tra danh sách bean thực trong `ApplicationContext` và loại class runtime.
4. Xem các cấu hình `@ConditionalOnMissingBean`, `@ConditionalOnClass` và property binding trong documentation/source của đúng Boot release.
5. Kiểm tra profile active và thứ tự config external overrides. `application.yml` không nhất thiết là nguồn cuối cùng nếu có environment variable hoặc command-line override.
6. Đối chiếu observed thread name, pool metrics và context wiring. Tên thread trùng prefix một mình chưa đủ để chứng minh mọi task dùng cùng executor, nhưng kết hợp với bean ID và future giúp chẩn đoán.

Với Framework thuần không có Boot, bạn vẫn xem bean definitions, `getBeansOfType` và cấu hình Java/XML; **không** có condition report của Boot nếu không sử dụng Boot.

## 8. Kiểm chứng runtime bằng code, không dựa vào phỏng đoán

### 8.1. Đếm các bean Executor và Scheduler

Fragment sau có thể đặt trong một component của dự án Boot hoặc Spring Framework; giả định đã inject `ApplicationContext context`, đã import Java `Map`, `Executor`, `TaskScheduler`, `ThreadPoolTaskExecutor`.

```java
Map<String, Executor> executors =
        context.getBeansOfType(Executor.class);

executors.forEach((name, executor) -> {
    String type = executor.getClass().getName();
    System.out.println("Executor " + name + " -> " + type);

    if (executor instanceof ThreadPoolTaskExecutor pool) {
        System.out.println("core=" + pool.getCorePoolSize());
        System.out.println("max=" + pool.getMaxPoolSize());
        System.out.println("poolSize=" + pool.getPoolSize());
        System.out.println("active=" + pool.getActiveCount());
    }
});

Map<String, TaskScheduler> schedulers =
        context.getBeansOfType(TaskScheduler.class);

schedulers.forEach((name, scheduler) ->
        System.out.println("Scheduler " + name + " -> " +
                           scheduler.getClass().getName()));
```

Đây là **fragment tích hợp**; không phải lớp Java độc lập. Nó giúp biết **bean hiện hữu và cấu hình** trong context. Tuy vậy, có bean không có nghĩa method thực tế đang dùng nó; phải truy thêm `@Async` qualifier, `AsyncConfigurer`, injection và các integration MVC/WebFlux.

Đừng lấy `getPoolSize()` rồi cho đó là `maxPoolSize`: pool size là số worker đang tồn tại tại thời điểm quan sát; max là cấu hình giới hạn. Và khi task đã chạy xong, `activeCount` có thể bằng 0 dù trước đó executor có làm việc.

### 8.2. Kiểm tra method `@Async` có thực sự đổi thread

Fragment cho service:

```java
@Async("domainExecutor")
public CompletableFuture<Boolean> onDomainPool() {
    return CompletableFuture.completedFuture(
            Thread.currentThread().getName().startsWith("domain-"));
}
```

Caller thuộc **bean khác** gọi service qua Spring proxy rồi kiểm tra `future.get(timeout)`. Không gọi `this.onDomainPool()` từ chính service để kiểm tra. Có thể ghi thêm trace ID, executor name và duration để đối chiếu trong môi trường test.

Với method trả `void`, không có future để truyền lỗi về caller; dùng `AsyncUncaughtExceptionHandler`/logging/monitoring phù hợp. Với `CompletableFuture`, exception được phản ánh khi future hoàn tất exceptional và caller quan sát nó.

### 8.3. Kiểm tra scheduling

Trong Spring, việc hiện diện một `ThreadPoolTaskScheduler` không chứng minh tất cả method `@Scheduled` đã được kích hoạt. Cần xem:

- Có `@EnableScheduling` và bean method được Spring quản lý không?
- Có scheduler phù hợp và được chọn đúng không?
- Cron zone, fixed rate/delay, concurrency và task overlap đã được hiểu đúng chưa?
- Có nhiều instance ứng dụng cùng chạy lịch không?
- Kết quả có yêu cầu exactly-once/durability vượt khả năng local scheduler không?

Một scheduled callback ngắn có thể chạy trên scheduler; callback kéo dài thường cần thiết kế tách tác vụ. Với nhiều replica, `@Scheduled` tự nó không bảo đảm chỉ chạy một lần toàn cụm.

## 9. Executor và scheduler: hai hệ auto-config riêng

Một ứng dụng có thể cần `@Async` nhưng không cần `@Scheduled`, hoặc ngược lại. Vì vậy cần phân biệt:

| Nhu cầu | Abstraction Framework | Hỗ trợ Boot có điều kiện | Property namespace tham khảo |
| --- | --- | --- | --- |
| Submit task bất đồng bộ | `TaskExecutor` / `AsyncTaskExecutor` | Executor auto-configured nếu thỏa điều kiện | `spring.task.execution.*` |
| Giới hạn pool worker async | `ThreadPoolTaskExecutor` | Chỉnh pool nếu loại bean đang là thread pool và được Boot quản lý | `spring.task.execution.pool.*` |
| Lên lịch task | `TaskScheduler` | Scheduler auto-configured khi cần và đủ điều kiện | `spring.task.scheduling.*` |
| Giới hạn scheduler worker | `ThreadPoolTaskScheduler` | Pool properties nếu dùng implementation pool tương ứng | `spring.task.scheduling.pool.*` |
| Chạy task với virtual threads | `SimpleAsyncTaskExecutor`/virtual-thread executor tùy phiên bản | Boot 3.3 hỗ trợ kích hoạt qua property | `spring.threads.virtual.enabled` |

Ví dụ Boot 3.3.x có thể dùng:

```yaml
spring:
  task:
    execution:
      thread-name-prefix: background-
      pool:
        core-size: 4
        max-size: 8
        queue-capacity: 64
    scheduling:
      thread-name-prefix: clock-
      pool:
        size: 2
```

Nếu chỉ khai báo `@EnableScheduling`, Boot có thể tự tạo scheduler theo điều kiện; nếu ứng dụng tự khai báo `ThreadPoolTaskScheduler`, đừng mặc định `spring.task.scheduling.pool.size` áp dụng vào bean đó. Nếu dùng virtual-thread scheduler của Boot, pool-size có thể không liên quan. Phải truy đúng object đang dùng.

### 9.1. Scheduler mặc định không phải durable job queue

Boot giúp tạo scheduler thuận tiện, nhưng việc tạo một bean scheduler không tự giải quyết:

- job phải sống sau khi JVM crash/restart;
- distributed lock cho nhiều instance;
- retry và idempotency;
- hệ thống lưu trạng thái thành công/thất bại;
- đảm bảo công việc hoàn thành một lần duy nhất trên toàn cluster.

Đó là bài toán quản lý job nghiệp vụ hoặc orchestration bên ngoài. Không biến auto-configuration thành lời hứa durability.

## 10. Virtual threads và khác biệt theo phiên bản Boot

Ở Java 21+, có thể dùng virtual threads cho nhiều công việc **blocking I/O**; điều đó không làm database/API downstream có vô hạn connection hay làm CPU-bound nhanh hơn số lõi.

Với Spring Boot 3.3.x khi có hỗ trợ phù hợp, `spring.threads.virtual.enabled=true` khiến auto-configured executor/scheduler thay đổi implementation. Boot có thể dùng:

- `SimpleAsyncTaskExecutor` với virtual threads thay cho `ThreadPoolTaskExecutor` được auto-configured;
- `SimpleAsyncTaskScheduler` với virtual threads thay cho `ThreadPoolTaskScheduler` trong trường hợp scheduling phù hợp.

Khi đó các property thuộc **pool platform threads** như core/max/queue/pool.size có thể không còn điều khiển cơ chế mới. Điều này chỉ áp dụng cho đường auto-configured tương ứng, không tự biến mọi custom `@Bean ThreadPoolTaskExecutor` thành virtual-thread executor.

Ví dụ Boot 3.3.x chạy trên Java 21+:

```yaml
spring:
  threads:
    virtual:
      enabled: true
  main:
    keep-alive: true
```

Virtual threads là daemon; với ứng dụng background/scheduled không có non-daemon thread khác giữ JVM sống, cấu hình keep-alive thích hợp giúp tránh thoát process ngoài ý muốn. Kiểm tra đúng phiên bản Boot và runtime triển khai.

**Không dùng “virtual thread = bật cờ xong hết vấn đề”.** Cần vẫn đo active tasks, CPU, memory, connection pool, timeout và backpressure. Với virtual-thread scheduler, một số chế độ fixed-delay có đặc tính scheduler thread cần lưu ý; đừng suy diễn rằng pool-size property sẽ mở rộng song song như thread pool cũ.

## 11. Ai tạo, ai đóng tài nguyên?

Không chỉ bean nào tồn tại mà **quyền sở hữu lifecycle** cũng khác nhau.

### 11.1. Tài nguyên được Spring quản lý

Khi `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler` là bean có lifecycle được Spring nhận biết, context sẽ thực hiện quá trình initialization/destroy phù hợp. Cả bean thủ công trong Framework và bean do Boot auto-configure đều có thể được Spring container quản lý.

Cấu hình shutdown của `ThreadPoolTaskExecutor` cần cân nhắc:

- `setWaitForTasksToCompleteOnShutdown(...)`: chính sách đợi/tiếp tục với task đã nhận khi context đóng, tùy behavior của Spring version.
- `setAwaitTerminationSeconds(...)`: giới hạn thời gian context đợi executor kết thúc theo cơ chế hỗ trợ; không phải cam kết mọi task sẽ hoàn tất.
- Retry/cancellation/timeout và external graceful shutdown nếu task có thể bị interrupt hay bị kill do container.

Nếu tác vụ nghiệp vụ bắt buộc tồn tại sau restart, executor trong memory không đủ: dùng durable job/queue/workflow phù hợp và đặt chính sách xử lý duplicate/idempotency.

### 11.2. Tài nguyên không do container quản lý

Ví dụ:

```java
public void process() {
    ExecutorService executor = Executors.newFixedThreadPool(4);
    executor.submit(() -> runWork());
}
```

Đây là **fragment sai về vòng đời** nếu không giữ/đóng `executor`. Spring/Boot không tự phát hiện và shutdown mọi executor được tạo trong local method. Cách hợp lý thường là tạo bean quản lý dùng lại hoặc bảo đảm code sở hữu executor đóng nó bằng `shutdown()`, chờ completion/hủy theo yêu cầu, và xử lý lỗi.

### 11.3. Lifecycle ownership theo nguồn bean

| Nguồn tài nguyên | Ai chọn cấu hình? | Ai thường quản lý lifecycle? |
| --- | --- | --- |
| `@Bean ThreadPoolTaskExecutor` trong Spring thuần | Code ứng dụng | Spring container nếu là managed bean |
| Auto-configured executor trong Boot | Boot + properties + conditions | Spring container |
| Custom `@Bean` trong Boot | Code ứng dụng / binding có chủ đích | Spring container |
| Local `Executors.new...` | Method/class tạo executor | Chính owner phải đóng |
| Jakarta EE managed executor | Container ứng dụng | Container bên ngoài; app không đóng tùy tiện |
| Broker/job worker | Infrastructure + worker manager | Theo vòng đời hệ job riêng |

Vì vậy, “Spring Framework manual” và “Spring Boot auto” khác nhau chủ yếu ở **nguồn bean definition và policy cấu hình**, còn lifecycle thực tế vẫn có thể cùng đi qua Spring container.

## 12. Cấu hình theo môi trường: local, test, staging, production

Trong Spring Framework thuần, bạn có thể tạo bean conditionally qua `@Profile`, `@Conditional` hoặc tự bind configuration ngoài. Trong Boot, auto-configuration và property sources giúp giảm boilerplate, nhưng dễ gây nhầm rằng giá trị ghi trong một YAML chắc chắn là giá trị cuối.

Các nguồn cấu hình Boot có thể gồm application.yml, profile-specific files, environment variables, system properties, command-line arguments và config import. Độ ưu tiên phụ thuộc quy tắc externalized configuration của Boot. Phải xác minh effective environment và bean runtime.

Ví dụ tưởng tượng:

- `application.yml`: `spring.task.execution.pool.core-size=4`;
- production profile: thay thành 8;
- custom `@Bean`: gọi `setCorePoolSize(2)`, không bind properties;
- task thực tế: `@Async("domainExecutor")` chạy trên custom bean.

Trong ví dụ, người xem YAML có thể nghĩ production chạy tám worker, nhưng **domainExecutor** vẫn có core bằng hai nếu không có logic khác ghi đè. Chính xác phải đọc bean đang chạy task và đường binding, không chỉ file cấu hình.

### 12.1. Một nguồn cấu hình có thể kiểm tra được

Nếu quyết định dùng custom bean vì yêu cầu nghiệp vụ đặc biệt, có thể làm như sau:

- Tạo namespace riêng, ví dụ `app.executors.domain.core-size` / `queue-capacity`, được bind rõ qua `@ConfigurationProperties`.
- Dùng values đó khi tạo `ThreadPoolTaskExecutor`.
- Validate giới hạn hợp lệ, ví dụ core không vượt max, queue không âm khi code không xử lý giá trị đặc biệt.
- Ghi metric và test property binding dưới profile production.
- Không đồng thời dùng hai nguồn mơ hồ mà không biết nguồn nào có ưu tiên.

Nếu chọn auto-configuration thuần, tránh tạo bean `Executor` không cần thiết có thể làm thay đổi conditions. Có thể cần một helper component chỉ inject `AsyncTaskExecutor` mà không khai báo executor mới.

## 13. Quan hệ với Spring MVC, WebFlux và transaction context

Spring MVC xử lý request trên servlet container threads, trong khi `@Async` task thường chạy trên executor của ứng dụng; MVC async controller return types có đường tích hợp executor riêng. Trong Boot 3.3, `applicationTaskExecutor` có ý nghĩa đối với một số tích hợp web. Nếu bạn dùng bean tên `domainExecutor` cho `@Async`, **đừng tự suy ra** Spring MVC async request cũng dùng chính bean đó.

Spring WebFlux ưu tiên non-blocking pipeline; không nên dùng pool tùy chỉnh rồi gọi blocking API trực tiếp trên event-loop. Hỗ trợ offload blocking của framework có quy tắc tích hợp riêng; xem hướng dẫn theo phiên bản và stack đang dùng.

Với transaction, Spring `@Transactional` thường gắn với thread thực thi theo cơ chế proxy/context. Chuyển sang `@Async` không khiến transaction ở caller tự động đi theo worker. Security context, MDC, request-scoped state cũng cần propagation có chủ đích. Những vấn đề này tồn tại trong cả Spring Framework thuần và Boot, vì Boot không làm biến mất thread boundary.

Một `TaskDecorator` có thể hỗ trợ sao chép một số context được phép, nhưng cần cleanup và kiểm thử khi thread pool tái sử dụng worker. Không chuyển toàn bộ request object hoặc EntityManager qua worker chỉ để giữ ngữ cảnh.

## 14. Các nguyên nhân lỗi và cách xử lý

| Hiện tượng | Khả năng thường gặp | Bước kiểm chứng |
| --- | --- | --- |
| `@Async` chạy trên request thread | Thiếu `@EnableAsync`, self-invocation, đối tượng không phải bean | In caller/worker thread, kiểm tra proxy và cấu hình |
| Có hai pool, task chạy “sai pool” | Nhiều `Executor`, tên/qualifier/default khác | Kiểm tra `@Async("...")`, `AsyncConfigurer`, bean `taskExecutor` |
| Đổi `spring.task.execution.pool.*` nhưng không thay đổi | Executor tự khai báo hoặc virtual-thread strategy | In actual class/core/max và đọc condition report |
| Không thấy bean `applicationTaskExecutor` | Auto-config back off do custom bean/conditions | Liệt kê beans và xem Boot conditions |
| MVC async không dùng custom `Executor` | Không đúng kiểu `AsyncTaskExecutor` hoặc tên phù hợp | Kiểm tra yêu cầu integration, cấu hình MVC |
| `@Scheduled` không chạy | Chưa enable hoặc method không phải Spring-managed bean | Xem `@EnableScheduling` và context |
| Lịch chạy nhiều lần trên cluster | Mỗi instance có scheduler riêng | Dùng coordination/lock, job idempotency |
| Shutdown còn nhiều task | Queue dài, task chậm, thiếu cancellation/timeout | Theo dõi queue, graceful shutdown và deadline |
| Boot dùng virtual thread nhưng pool-size không tác dụng | Implementation không phải thread pool platform threads | Xem class runtime, property virtual threads |
| Bean executor có tên đúng nhưng không có metric | Thiếu instrument hoặc lấy nhầm bean | Lấy object identity/name, thêm metric đúng pool |
| Lỗi thiếu bean khi đổi từ Framework sang Boot | Tin rằng starter luôn kích hoạt mọi annotation | Xác minh @EnableAsync/@EnableScheduling và conditions |
| Test chạy ổn nhưng production lỗi | Test dùng SyncTaskExecutor, runtime dùng pool async | Test có executor thật và đồng bộ bằng latch |

### 14.1. Thứ tự điều tra khi “properties không có hiệu lực”

1. Lấy chính xác phiên bản Java, Spring Framework và Spring Boot.
2. Xác định tác vụ ở đâu: `@Async` method, MVC async controller, scheduler callback hay gọi trực tiếp `executor.execute()`.
3. Xác định bean thực được chọn bởi qualifier/configurer/integration.
4. In bean name, runtime type, core/max/queue, thread prefix; đo bằng metric.
5. Kiểm tra bean đó do app `@Bean` tạo hay do Boot auto-configured.
6. Kiểm tra effective environment, profiles, properties và config binding.
7. Đọc condition evaluation report để biết tại sao Boot có/không tạo bean mặc định.
8. Sửa ở đúng nguồn cấu hình rồi tái kiểm tra task bằng thread name và load test.

Không tăng max thread khi chưa hiểu queue policy. Với `ThreadPoolExecutor`, pool thường dùng core workers trước, sau đó đưa task vào queue; chỉ khi queue không nhận thêm mới cần tăng worker tới max. Queue vô hạn có thể khiến max không phát huy như kỳ vọng.

## 15. Học qua hai trường hợp so sánh

### Tình huống A: Spring Framework thuần, muốn xử lý import 200 file

Bạn khai báo `@Bean("importExecutor")` với `ThreadPoolTaskExecutor`, đặt core/max/queue và rejection policy. Dùng `@EnableAsync`, đặt `@Async("importExecutor")` trên method thuộc Spring-managed bean và gọi từ bean khác.

Phương pháp kiểm tra: code `@Configuration` là nguồn bean definition; thread prefix xác nhận task dùng đúng pool; context close kiểm tra lifecycle. Nếu muốn chỉnh theo profile, bạn phải chủ động xây cơ chế nhận giá trị cấu hình (hoặc điều kiện bean phù hợp).

### Tình huống B: Spring Boot 3.3.x, ứng dụng MVC cần background work nhẹ

Nếu không cần custom executor, có thể để Boot auto-configure `applicationTaskExecutor`, dùng `spring.task.execution.*` để điều chỉnh. Vẫn bật `@EnableAsync` cho method annotation. Khi thêm custom `Executor` cho import, kiểm tra lại đường auto-configuration và MVC async integration.

Phương pháp kiểm tra: Boot condition report xác định bean auto-config, `ApplicationContext` xác nhận tên/kiểu, thread prefix và metrics xác nhận thực thi; properties chỉ được xem là hiệu lực khi thuộc đúng bean đã bind.

### Cùng một code nghiệp vụ, hai đường cấu hình

```java
@Service
public class ImportService {
    @Async("importExecutor")
    public CompletableFuture<Integer> importFiles(List<String> paths) {
        return CompletableFuture.completedFuture(paths.size());
    }
}
```

Đây là **fragment cần import và project Spring**; bạn phải có bean `importExecutor` trong cả hai môi trường nếu dùng qualifier này. Dùng Spring Boot **không tự suy ra** rằng một bean tên `importExecutor` được tạo bởi auto-configuration: Boot có thể tạo bean mặc định tên khác. Để dùng `@Async` không có qualifier, bạn lại phải kiểm chứng executor mặc định được resolve ở từng môi trường.

## 16. Bài thực hành kiểm tra sự khác biệt

Hãy xây **hai ứng dụng nhỏ** có cùng service `WorkerService` dùng `@Async`, cùng phương thức tính một kết quả đơn giản:

**Phần 1 — Framework thuần:**
1. Tạo `AnnotationConfigApplicationContext`, `@Configuration` và `@EnableAsync`.
2. Định nghĩa `@Bean("manualExecutor") ThreadPoolTaskExecutor` có prefix `manual-`, core 2, max 4, queue 10.
3. Dùng `@Async("manualExecutor")`, gọi qua một Spring-managed bean.
4. In thread name và chờ `CompletableFuture.get(timeout)`; xác nhận prefix.
5. Đóng context và xác minh task không nhận thêm khi executor đã shutdown.

**Phần 2 — Boot:**
1. Tạo dự án Boot 3.3.x, thêm `@SpringBootApplication` và `@EnableAsync`.
2. Không tạo `Executor` tùy chỉnh; đặt `spring.task.execution.thread-name-prefix=boot-` và các thuộc tính pool.
3. Liệt kê bean `applicationTaskExecutor` và quan sát class/runtime config.
4. Thêm `@Bean("customExecutor")` với prefix `custom-`; khởi động lại.
5. Ghi nhận bean nào còn tồn tại, vì sao auto-config có thể back off, method `@Async` sử dụng bean nào.
6. Đặt `@Async("customExecutor")`, kiểm tra task chuyển sang pool đúng.
7. Nếu dùng Spring MVC async, kiểm tra riêng bean `applicationTaskExecutor` và kiểu `AsyncTaskExecutor`.

**Phần 3 — Scheduling và môi trường:**
1. Thêm `@EnableScheduling` và một method `@Scheduled(fixedDelay = 5000)`.
2. Khi chưa có custom scheduler, quan sát Boot scheduler bean khi điều kiện thỏa.
3. Thêm custom `ThreadPoolTaskScheduler`, xem property `spring.task.scheduling.pool.size` còn tác dụng với bean nào.
4. Chạy trên Java 21+ và bật virtual threads (nếu release hỗ trợ), so sánh loại executor/scheduler và ý nghĩa pool-size.
5. Chạy hai replica mô phỏng và xác minh scheduler tại mỗi process; đề xuất cơ chế phối hợp nếu chỉ được chạy một job toàn cụm.

**Phần 4 — Kiểm thử và quan sát:**
1. Dùng queue hữu hạn, nộp nhiều task hơn capacity để quan sát rejection. Không dựa vào `sleep` để đoán thứ tự; dùng latch để giữ worker.
2. Đo core/max, active count, queue depth và độ trễ.
3. Đóng context khi còn task; kiểm tra shutdown policy và timeout.
4. Ghi lại “nguồn cấu hình → bean → caller/annotation → thread → lifecycle” cho từng tình huống.

### Checklist tự đánh giá

- [ ] Tôi phân biệt được `@Configuration`/`@Bean` của Framework và auto-configuration theo điều kiện của Boot.
- [ ] Tôi biết `@EnableAsync`/`@EnableScheduling` và việc tạo resource executor/scheduler là hai hành động riêng.
- [ ] Tôi có thể dự đoán **khi nào** Boot không tạo bean mặc định vì custom `Executor`.
- [ ] Tôi hiểu khác biệt về tên/kiểu bean `taskExecutor`, `applicationTaskExecutor` và qualifier của `@Async`.
- [ ] Tôi không mặc định `spring.task.execution.pool.*` chỉnh mọi custom executor.
- [ ] Tôi biết vì sao Spring MVC async và method `@Async` có thể dùng executor khác nhau.
- [ ] Tôi biết virtual threads làm thay đổi ý nghĩa pool properties ở đường auto-config tương ứng.
- [ ] Tôi xác định được ai sở hữu executor và ai shutdown khi ứng dụng dừng.
- [ ] Tôi có thể chứng minh bằng runtime bean inspection, condition report và test task thực sự chạy.
- [ ] Tôi biết kiểm chứng các quy tắc trên theo **Spring Boot release đang dùng**, thay vì sao chép một default từ version khác.

**Kết luận kiến thức:** Spring Framework cung cấp **cơ chế và abstraction** để cấu hình tài nguyên thực thi; Spring Boot cung cấp **bean và giá trị mặc định có điều kiện** nhằm giảm cấu hình thủ công. Để hiểu ứng dụng concurrency đang chạy ra sao, phải lần theo **annotation → executor/scheduler bean → nguồn tạo bean → properties/binding → thread và vòng đời thực tế**.

## 17. Tài liệu chính thức tham chiếu theo phiên bản

- Spring Framework — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `TaskScheduler`, `@EnableAsync`, `@EnableScheduling`, lựa chọn implementation và qualification.
- Spring Boot 3.3 — [Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): điều kiện auto-configured executor/scheduler, bean name `applicationTaskExecutor`, pool properties và virtual threads.
- Spring Boot — [Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, profile và quy tắc override.
- Spring Boot — [SpringApplication và Virtual Threads](https://docs.spring.io/spring-boot/reference/features/spring-application.html): JDK yêu cầu, property `spring.threads.virtual.enabled` và keep-alive.

Tài liệu hiện hành có thể thay đổi khi nâng Spring Framework/Boot. Với một dự án cụ thể, **kiểm tra tài liệu khớp phiên bản dependency và bean/condition report tại runtime** trước khi áp dụng mặc định vào production.
