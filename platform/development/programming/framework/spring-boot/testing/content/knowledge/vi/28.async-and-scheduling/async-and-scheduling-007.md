# Kiểm soát việc tự chạy scheduler khi khởi động context test trong Spring Boot

> **Module:** Spring Boot – testing  
> **Nhóm:** Bất đồng bộ và lịch chạy  
> **Đề bài:** Kiểm soát việc tự chạy scheduler khi khởi động context test  
> **Mục tiêu:** Ngăn `@Scheduled` vô tình thực thi khi `@SpringBootTest` khởi tạo context; phân biệt annotation processing, cron, executor pool và business handler; thiết kế cấu hình có điều kiện và kiểm thử chính xác cả scheduler-off, cron-off và scheduler-on bằng Java 17, Spring Boot 3.5, JUnit Jupiter.

## 1. Vấn đề thực tế

Một ứng dụng có job dọn lịch sử giao dịch, tính hóa đơn, đồng bộ API ngoài hoặc gửi email định kỳ. Test chỉ nhằm kiểm tra service, repository hoặc REST controller, nhưng `@SpringBootTest` nạp một Spring `ApplicationContext` gần đầy đủ.

Nếu cấu hình `@EnableScheduling` được nạp, Spring đăng ký các methods `@Scheduled` khi context hoàn tất refresh. Job có thể tự chạy ở scheduler thread **trước khi một assertion của JUnit bắt đầu**; hoàn toàn không cần test gọi trực tiếp method đó.

Hậu quả:

- Background job xóa/sửa fixtures đang dùng trong test.
- Test xanh khi chạy riêng, đỏ khi chạy cùng suite hoặc chạy song song.
- Gọi nhầm mail/API/Redis/Kafka/database thật vì test chưa thay connection details.
- Scheduler chạy trên thread khác nên không rollback theo `@Transactional` của test method.
- Mock HTTP client đã khai báo nhưng job có thể tick trước khi test stub behavior.
- `ApplicationContext` được cache sau test class, giữ scheduler hoạt động khi class khác chạy.
- Cron quá ngắn gây request/duplicate/lock contention.
- CI load khác developer khiến thời điểm tick không xác định, tạo flaky tests.
- Một JVM test bật scheduler dù bài kiểm thử không liên quan lịch chạy.
- Các ứng dụng nhiều replicas có thể trigger cùng một cron ở nhiều instances.

**Quy tắc:** Test không cần cron thì tắt scheduling registration **trước** context refresh. Test có mục tiêu scheduling mới bật cơ chế đó, dùng observation có timeout và cô lập external resources.

### 1.1. Luồng xử lý annotation scheduling

```text
@SpringBootTest starts ApplicationContext
                |
                v
       Configuration imported
                |
         @EnableScheduling?
            /       \
          no         yes
          |           |
          v           v
@Scheduled not    ScheduledAnnotationBeanPostProcessor
activated         scans managed @Scheduled beans
                      |
                 registers triggers
                      |
                   TaskScheduler
                      |
                 background thread
                      |
                job/adapter method
                      |
                business service
                      |
             database/API/queue effects
```

`@Scheduled` chỉ mô tả trigger. `@EnableScheduling` (hoặc registration tương đương) bật cơ chế phát hiện và đăng ký annotated methods. Một bean `TaskScheduler` tự nó không chứng minh các `@Scheduled` methods đã được đăng ký; ngược lại Spring có thể tạo fallback local scheduler khi processor đã đăng ký tasks mà không tìm được TaskScheduler bean phù hợp.

### 1.2. Những thứ phải phân biệt

| Thành phần | Tác dụng | Tắt bằng cách nào? |
| --- | --- | --- |
| `@EnableScheduling` | Bật processing của `@Scheduled` | Không import config có annotation trong test |
| `ScheduledAnnotationBeanPostProcessor` | Đăng ký phương thức theo trigger | Loại scheduling infrastructure trước refresh |
| `@Scheduled(cron=...)` | Lịch theo biểu thức cron | Property cron giá trị `-` |
| `@Scheduled(fixedRate=...)` | Lên lịch theo khoảng giữa các lần bắt đầu | Điều kiện hóa config/bean, không dùng `-` |
| `@Scheduled(fixedDelay=...)` | Chờ sau khi lần trước hoàn thành | Điều kiện hóa config/bean, không dùng `-` |
| `TaskScheduler` | Executor thực thi task được đăng ký | Pool config không tự tắt registration |
| Business service | Thực hiện nghiệp vụ | Gọi trực tiếp không cần scheduler |
| Quartz | Scheduler riêng của Quartz | Quartz-specific configuration |
| `@Async` | Asynchronous method execution | `@EnableAsync`/Executor configuration riêng |

## 2. Spring Framework: `@EnableScheduling` và `@Scheduled`

Một cấu hình tối giản:

```java
@Configuration
@EnableScheduling
class SchedulingConfiguration {
}
```

Đây là snippet Java, không phải file đầy đủ. Khi được import vào Spring context, `@EnableScheduling` bật `ScheduledAnnotationBeanPostProcessor`; processor quét các beans `@Scheduled` và đăng ký các tasks tương ứng.

### 2.1. Các loại trigger

```java
@Scheduled(
        fixedDelay = 5,
        timeUnit = TimeUnit.SECONDS)
public void reconcile() { /* ... */ }

@Scheduled(
        fixedRate = 5,
        timeUnit = TimeUnit.SECONDS)
public void refresh() { /* ... */ }

@Scheduled(
        cron = "0 */5 * * * *",
        zone = "UTC")
public void aggregate() { /* ... */ }
```

- **fixedDelay:** chờ giữa thời điểm task hoàn thành và lần bắt đầu tiếp theo.
- **fixedRate:** đặt lịch theo khoảng giữa các lần bắt đầu, behavior khi công việc dài phụ thuộc scheduler/concurrency.
- **initialDelay:** trì hoãn lần khởi chạy đầu của trigger tương ứng, nhưng không phải disable switch.
- **cron:** Spring dùng sáu trường giây, phút, giờ, ngày trong tháng, tháng, ngày trong tuần.
- `@Scheduled` có thể lặp trên một method, tạo nhiều trigger độc lập.

Không hiểu nhầm cron Spring là cron hệ điều hành chỉ có năm trường. Ví dụ `*/1 * * * * *` chạy một lần mỗi giây, chỉ nên dùng trong test sandbox có khả năng quan sát rõ.

### 2.2. CRON_DISABLED = `-`

Spring Framework hỗ trợ `Scheduled.CRON_DISABLED` (cũng có trong `ScheduledTaskRegistrar`) với giá trị chính xác **một dấu gạch nối**. Nó hữu ích khi cron expression lấy từ property:

```java
@Scheduled(cron = "${app.jobs.cleanup.cron:-}")
public void cleanup() {
    // ...
}
```

```properties
# application-test.properties
app.jobs.cleanup.cron=-
```

Spring không đăng ký cron trigger được resolve thành `-`. Method vẫn là Java method bình thường; vẫn có thể bị gọi thủ công hoặc từ một nguồn khác. **Cron sentinel không tắt fixedRate/fixedDelay** và không xóa những `@Scheduled` triggers khác trên cùng bean.

Ví dụ không hợp lệ:

```java
@Scheduled(fixedDelayString = "${app.jobs.delay:-}")
public void run() {
}
```

Nếu `app.jobs.delay` thành `-`, không có hợp đồng Spring Framework nói rằng fixed delay được disable. Chọn conditional registration hoặc cron trigger có disabled sentinel phù hợp, không coi dấu gạch nối là duration.

### 2.3. Cần property trước khi Spring register tasks

Các cấu hình như `app.jobs.cleanup.cron` được resolve khi Spring khởi tạo context và đăng ký schedules. Đổi một `System.setProperty` hoặc static flag ở `@BeforeEach` **sau khi context refresh** không tự hủy lịch đã đăng ký và không bảo đảm trigger được tái tạo.

Tương tự, job có thể được gọi từ `@PostConstruct` hay `ApplicationRunner` trước `@BeforeEach`. Tắt cron chỉ kiểm soát cron registration, không ngăn những lifecycle callbacks.

## 3. Không nhầm Boot scheduler pool config với công tắc tắt lịch

Spring Boot 3.5 tài liệu hóa các properties:

```properties
spring.task.scheduling.pool.size=2
spring.task.scheduling.thread-name-prefix=scheduling-
spring.task.scheduling.shutdown.await-termination=false
```

Đây là cấu hình **TaskScheduler implementation**, không phải feature toggle của `@EnableScheduling`. `pool.size=1` không ngăn job chạy hoặc giới hạn job chỉ chạy một lần. Đặt pool size 0 không phải giải pháp disable được hỗ trợ.

**Điểm dễ mắc:** `spring.task.scheduling.enabled=false` không phải một universal built-in flag được tài liệu Spring Boot 3.5 đảm bảo sẽ tắt mọi `@Scheduled`. Nếu dự án có custom logic dùng một property tên như vậy, phải kiểm tra code đó. Nếu chỉ thêm property rồi hy vọng framework tự áp dụng, tests có thể xanh giả.

Giải pháp bền vững là **tự định nghĩa feature switch** như `app.scheduling.enabled` và đặt `@ConditionalOnProperty` trên configuration chứa `@EnableScheduling`.

### 3.1. Vì sao không mock `TaskScheduler`?

Nếu annotation processor đã tồn tại, nó có thể đăng ký tasks với scheduler được cung cấp hoặc scheduler fallback. Một Mockito mock `TaskScheduler` có thể làm tasks không chạy vì mock không thực sự schedule, nhưng đó không chứng minh application đã disable schedules trong production-like context. Mock còn có thể không trả `ScheduledFuture` có ý nghĩa.

Tắt scheduling registration bằng configuration là mô hình rõ ràng hơn. Với positive test, dùng scheduler thật và bounded wait để kiểm tra.

### 3.2. Vì sao `@DirtiesContext` không đủ?

`@DirtiesContext` quản lý việc loại `ApplicationContext` khỏi cache/đóng context. Nó không ngăn scheduled task tick **ngay khi context đang sống**, trước khi class kết thúc. Dùng nó khi test cần scheduler on rồi phải đóng sau class, không dùng như công tắc scheduler-off.

### 3.3. Vì sao `@Transactional` không đủ?

JUnit test method transaction thường gắn với **test thread**. Một scheduler thread dùng DataSource/transaction khác có thể ghi và commit DB bất chấp test rollback. Nếu test không cần scheduler, tắt nó. Nếu cần scheduler, dùng DB test-only, cô lập fixtures, kiểm soát commit/retry và cleanup.

## 4. Thiết kế khuyến nghị: business service tách scheduled adapter

```text
BatchService
   └── business method runOnce()
            ▲
            │
BatchScheduleAdapter
   └── @Scheduled(cron=...)
            ▲
            │
SchedulingConfiguration
   └── @EnableScheduling (conditional)
```

Lý do:

- Service được test bằng pure JUnit/Mockito không cần clock hoặc thread pool.
- Adapter có thể gọi trực tiếp mà không cần Spring schedule.
- Context-off test vẫn có business service và adapter, chỉ thiếu annotation processor.
- Cron-off test có thể xác minh scheduler infrastructure vẫn tồn tại nhưng trigger của job cụ thể disabled.
- Context-on test xác minh task registration và một lần thực thi thực sự.
- External dependencies của service dễ thay bằng fake/mock phù hợp ở integration tests.

## 5. Dự án runnable Java 17 + Spring Boot 3.5.0

Ví dụ dưới đây không dùng DB, email, queue hay HTTP. Một service đếm số lần chạy bằng `AtomicInteger` và đẩy tín hiệu vào `BlockingQueue` để test có thể chờ việc scheduler đã thực thi.

Có **6 JUnit `@Test` methods**: 2 unit, 2 context-off, 1 cron-off, 1 context-on.

### 5.1. Cấu trúc

```text
scheduler-startup-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/schedulelab/
    │   ├── ScheduleLabApplication.java
    │   ├── SchedulingConfiguration.java
    │   ├── BatchService.java
    │   └── BatchScheduleAdapter.java
    └── test/java/com/example/schedulelab/
        ├── BatchServiceUnitTest.java
        ├── SchedulingOffContextTest.java
        ├── CronOffContextTest.java
        └── SchedulingOnContextTest.java
```

Mọi public Java class nằm trong file cùng tên, package `com.example.schedulelab`.

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>scheduler-startup-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Spring Boot parent quản lý dependency versions, JUnit Jupiter, AssertJ. Không cần Docker để chạy ví dụ này.

### 5.3. `ScheduleLabApplication.java`

```java
// src/main/java/com/example/schedulelab/ScheduleLabApplication.java
package com.example.schedulelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ScheduleLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScheduleLabApplication.class, args);
    }
}
```

**Cố ý không đặt `@EnableScheduling` tại application root.** Nếu đặt trực tiếp trên `@SpringBootApplication`, những `@SpringBootTest` nạp root config có thể bật scheduling mà custom property test không điều khiển được.

### 5.4. `SchedulingConfiguration.java`

```java
// src/main/java/com/example/schedulelab/SchedulingConfiguration.java
package com.example.schedulelab;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        name = "app.scheduling.enabled",
        havingValue = "true",
        matchIfMissing = true)
@EnableScheduling
public class SchedulingConfiguration {
}
```

- `app.scheduling.enabled=true`: load config và bật annotation scheduling.
- `app.scheduling.enabled=false`: loại config và không đăng ký processor từ config này.
- `matchIfMissing=true`: production/normal app bật mặc định nếu không có property. Nếu muốn opt-in toàn môi trường, thay default policy cho phù hợp.
- `app.scheduling.enabled` là property **do ứng dụng tự định nghĩa**, không phải built-in universal Spring Boot switch.
- Nếu có một config thứ hai cũng chứa `@EnableScheduling`, nó có thể vẫn bật processor. Hãy kiểm kê tất cả sources khi áp dụng vào project thật.

### 5.5. `BatchService.java`

```java
// src/main/java/com/example/schedulelab/BatchService.java
package com.example.schedulelab;

import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class BatchService {

    private final AtomicInteger completed = new AtomicInteger();
    private final BlockingQueue<Integer> signals =
            new LinkedBlockingQueue<>();

    public int runOnce() {
        int n = completed.incrementAndGet();
        signals.offer(n);
        return n;
    }

    public int count() {
        return completed.get();
    }

    public Integer awaitRun(Duration timeout)
            throws InterruptedException {
        return signals.poll(
                timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
```

`AtomicInteger` và `BlockingQueue` giúp test thread quan sát được tín hiệu từ scheduler thread. Đây là một demo in-memory state; nếu nghiệp vụ thật ghi DB hoặc gửi email, cần dùng test-only connections/mocks và assert side effect tương ứng.

### 5.6. `BatchScheduleAdapter.java`

```java
// src/main/java/com/example/schedulelab/BatchScheduleAdapter.java
package com.example.schedulelab;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class BatchScheduleAdapter {

    private final BatchService service;

    public BatchScheduleAdapter(BatchService service) {
        this.service = service;
    }

    @Scheduled(
            cron = "${app.batch.cron:*/2 * * * * *}",
            zone = "${app.batch.zone:UTC}")
    public void tick() {
        service.runOnce();
    }
}
```

- `app.scheduling.enabled=false` ngăn annotation processing; bean và method vẫn có mặt.
- `app.batch.cron=-` tắt **cron trigger** của adapter.
- `app.scheduling.enabled=true` với cron hợp lệ cho phép Spring đăng ký và gọi `tick()`.
- `*/2 * * * * *` chạy mỗi hai giây trong demo; không mang thiết lập này sang job production có tác động bên ngoài.
- `zone=UTC` giúp tránh ngẫu nhiên lệch giờ giữa local/CI. Những jobs theo lịch ngày/tuần vẫn phải có test calendar và DST riêng.

## 6. Unit tests: không Spring context

### 6.1. `BatchServiceUnitTest.java`

```java
// src/test/java/com/example/schedulelab/BatchServiceUnitTest.java
package com.example.schedulelab;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class BatchServiceUnitTest {

    @Test
    void incrementsAndSignalsCompletion() throws Exception {
        BatchService service = new BatchService();

        assertThat(service.count()).isZero();
        assertThat(service.runOnce()).isEqualTo(1);
        assertThat(service.awaitRun(
                Duration.ofMillis(100))).isEqualTo(1);
        assertThat(service.count()).isEqualTo(1);
    }

    @Test
    void adapterCanInvokeServiceWithoutScheduler() {
        BatchService service = new BatchService();
        BatchScheduleAdapter adapter =
                new BatchScheduleAdapter(service);

        adapter.tick();

        assertThat(service.count()).isEqualTo(1);
    }
}
```

Hai tests chỉ kiểm tra Java logic; không có Spring context hoặc scheduling thread. Chúng không chứng minh Spring đã đăng ký cron.

## 7. Context-off: xác nhận Spring không đăng ký `@Scheduled`

### 7.1. `SchedulingOffContextTest.java`

```java
// src/test/java/com/example/schedulelab/SchedulingOffContextTest.java
package com.example.schedulelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.scheduling.annotation.ScheduledAnnotationBeanPostProcessor;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "app.scheduling.enabled=false",
        "app.batch.cron=*/1 * * * * *"
})
class SchedulingOffContextTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    BatchService service;

    @Autowired
    BatchScheduleAdapter adapter;

    @Test
    void hasNoScheduledAnnotationProcessor() {
        assertThat(context.getBeansOfType(
                ScheduledAnnotationBeanPostProcessor.class))
                .isEmpty();
    }

    @Test
    void jobMethodRemainsCallable() {
        int before = service.count();

        adapter.tick();

        assertThat(service.count())
                .isEqualTo(before + 1);
    }
}
```

Cron property cố ý đặt mỗi giây để cho thấy **việc tắt infrastructure mới quyết định không đăng ký task**, không phải cron quá chậm. Test đầu khẳng định absence của processor. Test thứ hai chứng minh adapter/business vẫn có thể được gọi thủ công.

Không assert `service.count()==0` trong cả hai methods: Spring context có thể được cache và JUnit không bảo đảm thứ tự methods. Cách before/after không phụ thuộc thứ tự và không cần reset shared state.

Ở một ứng dụng có external custom schedulers, việc không có processor chỉ chứng minh không có Spring annotation scheduling theo phạm vi đó; nó **không** chứng minh không có Quartz/Timer/`ApplicationRunner`.

## 8. Context cron-off: infrastructure có nhưng một job bị tắt

### 8.1. `CronOffContextTest.java`

```java
// src/test/java/com/example/schedulelab/CronOffContextTest.java
package com.example.schedulelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.scheduling.annotation.ScheduledAnnotationBeanPostProcessor;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "app.scheduling.enabled=true",
        "app.batch.cron=-"
})
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class CronOffContextTest {

    @Autowired
    ScheduledAnnotationBeanPostProcessor processor;

    @Autowired
    BatchService service;

    @Test
    void processorExistsButCronTriggerIsAbsent() {
        assertThat(processor).isNotNull();
        assertThat(processor.getScheduledTasks()).isEmpty();
        assertThat(service.count()).isZero();
    }
}
```

Trong demo chỉ có một `@Scheduled` method; vì trigger bị disable nên `getScheduledTasks()` trống. Với ứng dụng có nhiều jobs khác, tổng scheduled task set có thể vẫn không trống. Không áp dụng assertion global này để suy ra một job cụ thể đã tắt khi vẫn có nhiều jobs đăng ký.

### 8.2. Trường hợp phù hợp để chọn cron-off

- Muốn giữ scheduler infrastructure nhưng tắt một job có side effect nặng.
- Muốn test những scheduled jobs khác vẫn active.
- Muốn verify conditional cron properties mà không bỏ toàn bộ config.
- Muốn ngăn một cron job ngay cả khi component bean vẫn injectable.

**Không dùng** cron disabled sentinel cho fixed-delay/rate properties hoặc để tắt method được `@PostConstruct` gọi thủ công.

## 9. Context-on: test một lần cron thực sự thực thi

### 9.1. `SchedulingOnContextTest.java`

```java
// src/test/java/com/example/schedulelab/SchedulingOnContextTest.java
package com.example.schedulelab;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.scheduling.annotation.ScheduledAnnotationBeanPostProcessor;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "app.scheduling.enabled=true",
        "app.batch.cron=*/1 * * * * *",
        "spring.task.scheduling.pool.size=1"
})
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class SchedulingOnContextTest {

    @Autowired
    ScheduledAnnotationBeanPostProcessor processor;

    @Autowired
    BatchService service;

    @Test
    void registersAndExecutesCronTask() throws Exception {
        assertThat(processor.getScheduledTasks())
                .isNotEmpty();

        Integer observed =
                service.awaitRun(Duration.ofSeconds(8));

        assertThat(observed).isNotNull();
        assertThat(observed).isGreaterThan(0);
        assertThat(service.count())
                .isGreaterThanOrEqualTo(observed);
    }
}
```

- `getScheduledTasks().isNotEmpty()` kiểm tra registration.
- `BlockingQueue.poll(Duration)` đợi có một execution signal, không dùng fixed sleep.
- Nếu cron tick trước khi JUnit method bắt đầu, signal đã nằm trong queue nên test vẫn thấy.
- Không assert đúng một execution; CI scheduling timing và context startup có thể khác.
- `@DirtiesContext(AFTER_CLASS)` đóng Spring context khi class kết thúc, tránh để scheduler tiếp tục tick từ cache sau test.
- `spring.task.scheduling.pool.size=1` chỉ điều chỉnh thread pool; nó không bật/tắt scheduler.

Test này chứng minh scheduler thực thi ít nhất một lần trong context đơn giản. Nó **không** chứng minh exactly once toàn cluster, correct DST behavior hoặc performance dưới tải.

## 10. Chạy project và kết quả dự kiến

```bash
java -version
mvn -version

mvn -B -ntp -Dtest=BatchServiceUnitTest test
mvn -B -ntp -Dtest=SchedulingOffContextTest test
mvn -B -ntp -Dtest=CronOffContextTest test
mvn -B -ntp -Dtest=SchedulingOnContextTest test

# Toàn bộ 6 JUnit methods:
mvn -B -ntp test
```

| Test class | Số `@Test` | Cơ chế |
| --- | ---: | --- |
| BatchServiceUnitTest | 2 | Business, không Spring |
| SchedulingOffContextTest | 2 | Scheduled processor không tồn tại |
| CronOffContextTest | 1 | Processor tồn tại, cron disabled |
| SchedulingOnContextTest | 1 | Processor tồn tại, cron được thực thi |
| **Tổng** | **6** | Đủ hai nhánh off/on |

Lệnh Maven là hướng dẫn tái hiện, không phải một lần chạy thực tế được ghi nhận khi soạn tài liệu. Output phụ thuộc JDK/Maven/Spring Boot version, và cron có thể tick vào thời điểm khác nhau trên mỗi máy.

## 11. Áp dụng vào ứng dụng có `@EnableScheduling` trên main application

Một anti-pattern:

```java
@SpringBootApplication
@EnableScheduling
public class Application {
}
```

`@SpringBootTest` có thể load root application và tự bật scheduling. Chỉ thêm `app.scheduling.enabled=false` **không có tác dụng** nếu `@EnableScheduling` trực tiếp trên main class không được condition hóa.

### 11.1. Refactor nên làm

1. Bỏ `@EnableScheduling` khỏi main application.
2. Tạo `SchedulingConfiguration` riêng như phần 5.4.
3. Thêm `@ConditionalOnProperty` để feature switch được đánh giá lúc context load.
4. Đặt flag false trên các tests không liên quan scheduling.
5. Viết một positive scheduler integration test bật flag.
6. Nếu có nhiều `@EnableScheduling` registrations ở các modules khác, đưa chúng về một cơ chế kiểm soát nhất quán.

Không xóa `@EnableScheduling` ở production mà quên kiểm thử rằng lịch được bật đúng trong deployment mode mong đợi.

### 11.2. `application-test.properties`

Có thể dùng file:

```text
src/test/resources/application-test.properties
```

với nội dung:

```properties
app.scheduling.enabled=false
app.batch.cron=-
```

Khi test muốn kích hoạt profile:

```java
@ActiveProfiles("test")
@SpringBootTest
class CustomerControllerTest {
    //...
}
```

Đây là annotation snippet; import `org.springframework.test.context.ActiveProfiles`. **Đặt file `application-test.properties` không tự activate profile test.** Dùng `@ActiveProfiles` hoặc configuration/environment khác có chủ đích. Spring TestContext có cache; cấu hình property và active profile cần được xác định trong context identity.

### 11.3. Condition hóa scheduled bean riêng

Nếu chỉ một job cần tắt:

```java
@Component
@ConditionalOnProperty(
        name = "app.jobs.cleanup.enabled",
        havingValue = "true",
        matchIfMissing = true)
class CleanupScheduleAdapter {

    @Scheduled(cron = "${app.jobs.cleanup.cron:0 0 * * * *}")
    void run() {
        // ...
    }
}
```

Khi flag false, bean không tồn tại; những class inject nó bắt buộc có thể fail. Giải pháp là tách `CleanupService` (nghiệp vụ) ra khỏi `CleanupScheduleAdapter` (trigger), chỉ condition hóa adapter.

### 11.4. `@Profile("!test")`

Cấu hình:

```java
@Configuration
@Profile("!test")
@EnableScheduling
class ProductionScheduling {
}
```

có thể hợp với dự án mà mọi test phải disable, nhưng sẽ khó viết scheduler-positive test dưới cùng profile `test`. Property flag thường linh hoạt hơn. Không đặt `@Profile("!test")` lên business service nếu tests cần gọi service đó.

## 12. Phân biệt Spring scheduling với các nguồn background work khác

| Nguồn tự chạy | Trigger | Công tắc liên quan |
| --- | --- | --- |
| Spring `@Scheduled` | Scheduled annotation processor | `@EnableScheduling`/cron flag |
| Programmatic `TaskScheduler.schedule` | Code đăng ký Runnable | Guard/config riêng |
| `@Async` | Proxy async call | `@EnableAsync`/TaskExecutor |
| Quartz | Quartz SchedulerFactoryBean | `spring.quartz.auto-startup` |
| Spring Batch startup job | JobLauncherApplicationRunner | Batch startup config |
| `ApplicationRunner` / `CommandLineRunner` | Spring application lifecycle | Condition hóa runner |
| `@PostConstruct` | Bean initialization | Condition hóa bean/callback |
| `ApplicationReadyEvent` | Application event | Conditional listener |
| Kafka/Rabbit listener | Listener containers | Listener auto-startup properties |
| Kubernetes CronJob | External orchestrator | Kubernetes schedule/suspend |

Trong Spring Boot 3.5, có documented property:

```properties
spring.quartz.auto-startup=false
```

Nó kiểm soát Quartz scheduler, **không** tắt Spring `@Scheduled`. Spring Batch cũng có cách tự launch jobs khi startup, không phải do Spring scheduling annotation processor. Nếu app có nhiều trigger mechanisms, cần map chúng riêng; không có một property thần kỳ ngăn mọi loại background job.

### 12.1. `@PostConstruct` và `ApplicationRunner` không bị disable

Nếu scheduled bean có `@PostConstruct` tự gọi business method, nó vẫn chạy ngay khi bean khởi tạo dù cron đã bằng `-`. Tương tự `ApplicationRunner` có thể chạy business logic khi Spring application ready.

Vì thế khi một side effect xuất hiện trong test dù đã disable scheduler, kiểm tra call site/stack trace và lifecycle callbacks. Không lập tức kết luận disabled cron convention không hoạt động.

### 12.2. Multi-instance scheduling

Spring `@Scheduled` là **một lịch trong mỗi application instance**. Nếu có ba replicas đều bật scheduler, cả ba có thể chạy job. Nếu cần toàn hệ thống chỉ một lần, dùng leader election/distributed lock/idempotency, hoặc một centralized scheduler. Một test local với một context không chứng minh tính duy nhất trên cluster.

## 13. Các cách kiểm tra mạnh hơn ngủ một khoảng thời gian

### 13.1. Kiểm tra absence processor

```java
assertThat(context.getBeansOfType(
        ScheduledAnnotationBeanPostProcessor.class))
        .isEmpty();
```

Mạnh hơn `Thread.sleep(50)` rồi assert counter vẫn zero, vì dù task active cũng có thể chưa tới lần tick đầu trong 50ms.

### 13.2. Kiểm tra tasks đã được đăng ký

```java
assertThat(processor.getScheduledTasks()).isNotEmpty();
```

Dùng cho context scheduler-on. Trong context cron-off demo có duy nhất một scheduled method, assert empty. Nếu app có nhiều jobs, phải xác định **đúng job** không đăng ký, thay vì chỉ xem tổng size của tất cả tasks.

### 13.3. Kiểm tra execution signal

```java
Integer observed =
        service.awaitRun(Duration.ofSeconds(8));
assertThat(observed).isNotNull();
```

Đoạn trên cần một service có BlockingQueue/latch hoặc business state test-only. Bounded await trả về sớm khi có tín hiệu và fail có giới hạn khi không. Không dùng sleep cố định rồi đoán.

### 13.4. Kiểm tra calendar/cron riêng

Có thể test `CronExpression.parse` và `next(...)` trên `ZonedDateTime` cố định, không đợi một cron theo giờ/ngày trong integration tests:

```java
CronExpression cron =
        CronExpression.parse("0 0 9 * * MON-FRI");

ZonedDateTime after =
        ZonedDateTime.of(
                2026, 11, 9, 8, 0, 0, 0,
                ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime next = cron.next(after);
```

Snippet cần imports từ `org.springframework.scheduling.support.CronExpression` và `java.time`. Dữ liệu minh họa là thứ Hai, 09/11/2026 lúc 08:00 tại `Asia/Ho_Chi_Minh`; cron trả thời điểm ngày đó lúc 09:00 (+07:00). Với zones có DST, phải thiết kế test cho những lần giờ bị nhảy/trùng.

### 13.5. Context caching

Spring TestContext caches `ApplicationContext` giữa các tests có cấu hình giống nhau. Nếu context active scheduler vẫn tồn tại trong cache, task có thể tiếp tục chạy ngay cả khi class đầu tiên đã kết thúc.

- Dùng test properties riêng cho scheduler-on/off.
- Với scheduler-on tests, `@DirtiesContext(AFTER_CLASS)` giúp close context đúng thời điểm.
- Không lạm dụng `@DirtiesContext` ở mọi class vì suite sẽ chậm.
- Không kỳ vọng thay static flag ở `@BeforeEach` khiến context đã cache được rebuild.
- Nếu test khác dùng chung DB, scheduler-on context phải được cô lập hoặc stop trước khi class khác dùng data.
- Nếu cần chạy JUnit parallel, dùng unique test fixtures và tránh shared mutable state giữa contexts.

## 14. Lỗi phổ biến và cách chẩn đoán

### Lỗi A — Tưởng `spring.task.scheduling.enabled=false` là built-in universal switch

Spring Boot 3.5 không tài liệu hóa property này như công tắc tắt annotation scheduling toàn ứng dụng. Dùng `@ConditionalOnProperty` trên config có `@EnableScheduling` và assert absence processor.

### Lỗi B — Tưởng `spring.task.scheduling.pool.size=0` sẽ tắt lịch

Pool size chỉ điều chỉnh executor, giá trị 0 có thể không hợp lệ. Không dùng làm feature flag.

### Lỗi C — Chỉ disable cron của một job nhưng job vẫn chạy

Kiểm tra có thêm `@Scheduled(fixedRate...)` trên method không, hoặc `@PostConstruct`/runner/controller gọi method trực tiếp không. Cron disabled không cấm Java invocation.

### Lỗi D — `fixedDelayString="-"` làm context startup fail

Dấu `-` là sentinel cho cron; fixed delay/rate cần duration hợp lệ. Dùng conditional registration/bean guard phù hợp.

### Lỗi E — Test chỉ assert counter=0 sau 100ms

Scheduler có thể chưa tick nên test xanh giả. Assert không có annotation processor hoặc no task registration thay vì suy từ khoảng thời gian ngắn.

### Lỗi F — Unit test dùng `@SpringBootTest` dù không cần Spring

Nạp context làm khởi động nhiều beans/background processes không liên quan; pure JUnit + Mockito thường nhanh và ít side effects hơn.

### Lỗi G — `@DirtiesContext` được đặt khắp nơi

Nó tốn thời gian và không ngăn task chạy trong lúc context active. Tắt registration bằng config cho các test không cần scheduler.

### Lỗi H — Test positive flaky khi chạy trên CI

Scheduler tick bất đồng bộ; dùng bounded signal thay vì sleep, không assert đúng một tick, đảm bảo runner có CPU phù hợp. Nếu timeout tăng lên rất lớn mà vẫn fail, kiểm tra logs/config và thread starvation.

### Lỗi I — Context off vẫn có bean TaskScheduler

Bean TaskScheduler có thể do custom code hoặc auto-config; không đủ kết luận annotation scheduling active. Kiểm tra postprocessor/registered tasks.

### Lỗi J — Test rollback mà job vẫn sửa DB

Scheduled thread không nằm trong test transaction; dùng DB test-only hoặc disable scheduler trong suite không chủ đích.

### Lỗi K — Spring context cache giữ job chạy giữa classes

Dùng distinct properties, quản lý lifecycle, `@DirtiesContext` có chủ đích và test data isolation.

### Lỗi L — Quartz vẫn chạy dù Spring cron đã tắt

Quartz tự có scheduler và properties; `spring.quartz.auto-startup=false` tác động Quartz, không tác động `@Scheduled`.

### Lỗi M — Multi-instance jobs chạy trùng

Mỗi replica có lịch riêng. Distributed locking/idempotency là quyết định kiến trúc, không được giải quyết chỉ bằng một flag trong test.

## 15. Checklist trước khi merge thay đổi test

- [ ] Đề bài test thuộc logic nghiệp vụ hay cần scheduler thực?
- [ ] `@EnableScheduling` nằm ở configuration có điều kiện khi muốn dễ tắt trong tests.
- [ ] Custom property thực sự được `@ConditionalOnProperty` tiêu thụ.
- [ ] Không dùng `spring.task.scheduling.pool.size` như một switch.
- [ ] Không giả định `spring.task.scheduling.enabled` là built-in universal flag.
- [ ] Chỉ dùng dấu `-` để disable cron, không dùng cho fixed rate/delay.
- [ ] Business method và scheduled adapter đã được tách rõ.
- [ ] Context-off test kiểm tra không có scheduled processor.
- [ ] Context cron-off test kiểm tra không đăng ký trigger cụ thể.
- [ ] Context-on test kiểm tra registered tasks và bounded execution.
- [ ] Scheduler-on tests được đóng context sau class nếu có nguy cơ cached background job.
- [ ] Test profile và property precedence đã được xác định rõ.
- [ ] Không dùng production DB/API/email/queue từ background task trong tests.
- [ ] Rollback của test thread không bị hiểu nhầm là rollback của scheduler thread.
- [ ] Quartz, Batch, runners và message listeners được quản lý bằng controls riêng.
- [ ] Nếu deploy nhiều replicas, có idempotency/coordination khi nghiệp vụ cần.
- [ ] CI không silently skip scheduler-positive tests, không dùng fixed sleeps để che lỗi.

## 16. Bài tập thực hành

**Bài 1:** Chạy `SchedulingOffContextTest` với cron một giây nhưng flag off. Giải thích vì sao absence postprocessor đáng tin hơn sleep vài mili-giây.

**Bài 2:** Chạy `CronOffContextTest`. Thêm một cron job thứ hai để thấy tắt cron của một job không làm processor ngừng xử lý những job khác.

**Bài 3:** Chạy `SchedulingOnContextTest`, đổi cron mỗi giây thành mỗi hai giây. Điều chỉnh bounded timeout và giải thích vì sao không assert exact number of runs.

**Bài 4:** Đưa `@EnableScheduling` lên main application root, giữ flag false và quan sát context-off assertion có thể fail. Refactor về conditional config đúng.

**Bài 5:** Thử đặt `fixedDelayString="-"`, xem lỗi startup và đề xuất một cách tắt schedule phù hợp hơn.

**Bài 6:** Thay BatchService bằng repository DB test-only, cho background thread ghi rồi chứng minh `@Transactional` trên JUnit test thread không bao quát transaction ấy.

**Bài 7:** Tạo hai Spring application contexts cùng enabled, thảo luận duplicate scheduling, distributed locks và idempotency.

**Bài 8:** So sánh Quartz `spring.quartz.auto-startup=false` với Spring annotation scheduling flag; phân loại nguồn trigger thật trước khi áp property.

## 17. Câu hỏi tự kiểm tra

**1.** Chỉ có `@Scheduled` thì method tự tick không? — Không theo annotation scheduling thông thường, cần enable processor.

**2.** `spring.task.scheduling.pool.size=1` có tắt lịch không? — Không.

**3.** `CRON_DISABLED` có giá trị gì? — `-`, chỉ dùng để vô hiệu hóa cron trigger.

**4.** Có thể dùng `fixedDelayString="-"` để tắt fixed delay không? — Không, đây không phải duration hợp lệ cho cơ chế đó.

**5.** Tại sao cần tách service và scheduled adapter? — Để unit test business không cần clock và điều kiện hóa trigger.

**6.** Tại sao scheduler thread không rollback theo JUnit test transaction? — Vì thường là một thread/transaction khác.

**7.** `@DirtiesContext` có tắt scheduling từ lúc startup không? — Không.

**8.** Tắt Spring `@Scheduled` có tắt Quartz không? — Không.

**9.** Vì sao positive test dùng BlockingQueue thay sleep? — Để bắt đúng completion signal với bounded timeout.

**10.** Ba replicas có nghĩa `@Scheduled` chạy một lần toàn cluster? — Không; mỗi JVM có thể đăng ký trigger riêng.

## 18. Tài liệu chính thức

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): annotation scheduling, cron, fixed rate/delay, TaskScheduler.
- [Spring Framework — Scheduled annotation](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html): CRON_DISABLED.
- [Spring Framework — ScheduledTaskRegistrar](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/config/ScheduledTaskRegistrar.html): task registration và dấu `-`.
- [Spring Framework — ScheduledAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/ScheduledAnnotationBeanPostProcessor.html): quét và đăng ký các @Scheduled methods.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): auto-configured schedulers và pool size.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): scheduling/quartz properties.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest, profiles, properties, context caching.
- [Spring Boot 3.5 — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): config có điều kiện.
- [Spring Framework — CronExpression](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/CronExpression.html): tính thời điểm cron kế tiếp.

**Kết luận:** Để tránh `@Scheduled` tự chạy khi Spring test context khởi tạo, phải kiểm soát **annotation registration trước refresh**, không chờ test method bắt đầu rồi mới tìm cách dừng. Đặt `@EnableScheduling` trong config có điều kiện, tắt cron riêng bằng `-`, tách business service khỏi scheduler adapter. Tests nên chứng minh hai nhánh off/on với structural assertions và bounded execution signal, đồng thời có lifecycle cleanup và test-only dependencies để không tạo side effects ngoài ý muốn.