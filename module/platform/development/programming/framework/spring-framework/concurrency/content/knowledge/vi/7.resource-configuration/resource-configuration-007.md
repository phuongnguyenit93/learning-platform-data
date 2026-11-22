# Cấu hình TaskExecutor và TaskScheduler bằng @Bean hoặc namespace task trong XML

## 1. Mục tiêu của cấu hình tài nguyên đồng thời

Spring Framework cung cấp các abstraction để **thực thi tác vụ** (`TaskExecutor`) và **lên lịch tác vụ** (`TaskScheduler`). Ứng dụng phải tạo và cấu hình implementation phù hợp, đưa nó vào Spring ApplicationContext và tiêm cho những thành phần cần dùng.

Có hai cách khai báo phổ biến trong Spring Framework:

1. **Java configuration**: viết method `@Bean` trong lớp `@Configuration`, tạo đối tượng executor/scheduler và cấu hình bằng setter.
2. **XML configuration**: dùng phần tử thuộc **task namespace**, chẳng hạn `<task:executor>`, `<task:scheduler>` và `<task:annotation-driven>`. XML cũng hỗ trợ cách thông thường qua `<bean class="...">` và `<property>`.

Hai cách có chung mục tiêu: đăng ký bean trong container, để business code dùng interface thay vì tự quản lý vòng đời thread pool. Việc chuyển Java sang XML không tự làm ứng dụng nhanh hơn; lựa chọn phụ thuộc vào cách cấu hình module, yêu cầu vận hành, cấu trúc dự án và mức độ dễ bảo trì.

```text
             Configuration, one choice per application/context
                  /                             \
       Java @Configuration                 Spring XML
       @Bean executor()                    <task:executor .../>
       @Bean scheduler()                   <task:scheduler .../>
                  \                             /
                   \                           /
               ApplicationContext / bean registry
                       |              |
                     TaskExecutor   TaskScheduler
                       |              |
                 submit Runnable   schedule a task
                       |              |
                     workers / clock / concurrency controls
```

Điểm thiết kế quan trọng: **bean definition** quyết định cách tạo và quản lý tài nguyên; **client code** chỉ cần biết hợp đồng cần dùng.

## 2. Phân biệt TaskExecutor và TaskScheduler trước khi cấu hình

| Đặc tính | `TaskExecutor` | `TaskScheduler` |
| --- | --- | --- |
| Mục đích | Nhận task để thực thi theo chính sách executor | Chạy task tại thời điểm chỉ định hoặc theo lịch |
| API tiêu biểu | `execute(Runnable)` | `schedule(...)`, các biến thể fixed-rate/fixed-delay |
| Implementation hay gặp | `ThreadPoolTaskExecutor` | `ThreadPoolTaskScheduler` |
| Cấu hình Java | Bean `ThreadPoolTaskExecutor` | Bean `ThreadPoolTaskScheduler` |
| Cấu hình XML rút gọn | `<task:executor .../>` | `<task:scheduler .../>` |
| Annotation liên quan | `@Async` | `@Scheduled` |

**Không nhầm lẫn:** chỉ khai báo bean executor không tự động kích hoạt `@Async`; chỉ khai báo scheduler không tự động kích hoạt `@Scheduled` trong Spring Framework thuần. Để xử lý annotation, cấu hình Java cần `@EnableAsync` / `@EnableScheduling` tương ứng, hoặc XML dùng `<task:annotation-driven .../>`.

Hai loại tài nguyên có thể tồn tại cùng lúc và phục vụ hai loại công việc khác nhau. Việc scheduler quyết định *khi nào* task chạy không giống executor thông thường quyết định *cách nào* task được nhận và phân phối cho worker.

## 3. Cấu hình ThreadPoolTaskExecutor bằng @Bean

Ví dụ method bean trong một lớp cấu hình Java:

```java
@Configuration(proxyBeanMethods = false)
public class TaskInfrastructureConfig {

    @Bean("workExecutor")
    public ThreadPoolTaskExecutor workExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("work-");
        return executor;
    }
}
```

Đây là **fragment**; cần import `org.springframework.context.annotation.Configuration`, `org.springframework.context.annotation.Bean` và `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor`. Bản chạy đầy đủ sẽ có ở mục 7.

Phân tích:

- `@Configuration` cho biết class chứa bean definitions. `proxyBeanMethods=false` phù hợp khi các method `@Bean` không gọi trực tiếp lẫn nhau để lấy bean do container quản lý.
- `@Bean("workExecutor")` đặt định danh ổn định cho executor. Có thể inject theo tên khi ứng dụng có nhiều executor.
- `corePoolSize=2`: pool tạo đến 2 core worker khi task được gửi (mặc định không nhất thiết tạo sẵn).
- `maxPoolSize=4`: giới hạn worker tối đa trong trường hợp queue không nhận được task.
- `queueCapacity=8`: chọn `LinkedBlockingQueue` có tối đa 8 task nằm chờ. Nếu `queueCapacity=0`, Spring dùng `SynchronousQueue` để handoff, không lưu backlog.
- `threadNamePrefix="work-"`: giúp nhận dạng threads trong log, thread dump và profiler.

Với queue dương, quy tắc tiếp nhận thông thường của `ThreadPoolExecutor` là **tạo core threads → xếp vào queue → tăng đến max nếu queue đầy → từ chối nếu pool/queue đều hết chỗ**. Do đó tăng riêng `maxPoolSize` mà giữ queue rất lớn có thể không làm pool mở rộng như mong đợi.

Các con số 2/4/8 trong bài chỉ phục vụ ví dụ. Trong production, phải dựa trên tải, CPU, thời gian task, giới hạn DB/HTTP, timeout và yêu cầu độ trễ để chọn giá trị.

### Lifecycle của bean executor

Khi `ThreadPoolTaskExecutor` là một Spring-managed bean, container áp dụng các lifecycle callback cần thiết để khởi tạo executor và phối hợp shutdown. Không cần gọi `afterPropertiesSet()` thủ công từ method `@Bean` rồi lại để Spring khởi tạo một lần nữa.

Trong chương trình độc lập tự tạo bằng `new ThreadPoolTaskExecutor()` mà **không** dùng container, người viết phải khởi tạo và dừng pool đúng cách. Cấu hình thông qua bean giúp một nơi chịu trách nhiệm này. Đối với tác vụ nền quan trọng, vẫn phải xem cấu hình chính sách shutdown/await-termination; không mặc định rằng tất cả task luôn hoàn tất khi ứng dụng thoát.

## 4. Cấu hình ThreadPoolTaskScheduler bằng @Bean

Để lên lịch công việc, có thể dùng:

```java
@Bean("workScheduler")
public ThreadPoolTaskScheduler workScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("schedule-");
    return scheduler;
}
```

Đây cũng là fragment, đặt trong lớp `@Configuration` và cần import `ThreadPoolTaskScheduler`. Nó có pool để xử lý các lần kích hoạt lịch, **không phải queueCapacity của executor thường**.

Nếu muốn Spring nhận diện method `@Scheduled`:

```java
@Configuration
@EnableScheduling
public class SchedulingConfig {
    // Các bean TaskScheduler và bean có method @Scheduled.
}
```

Một method được Spring quản lý có thể khai báo:

```java
@Scheduled(fixedDelay = 5_000)
public void refreshCache() {
    // Phần xử lý làm mới cache.
}
```

Các fragment này cần `org.springframework.scheduling.annotation.EnableScheduling` và `Scheduled`. Đây là **minh họa ngữ nghĩa**, không phải chương trình chạy độc lập. `fixedDelay` đo độ trễ sau khi **lần thực thi trước kết thúc**; `fixedRate` biểu diễn chu kỳ tính từ mốc bắt đầu theo cơ chế scheduler. Với nhiều thread, tác vụ dài, retry và tài nguyên chung, phải phân tích khả năng chồng lấn, độ trễ và tính idempotent; không coi scheduling là bảo đảm xử lý chính xác một lần trong hệ phân tán.

## 5. Namespace task trong Spring XML

Cú pháp namespace cho phép mô tả cấu hình tài nguyên mà không phải liệt kê đầy đủ tên lớp cho mỗi bean.

### 5.1. Khai báo namespace và schema

Phần đầu một XML context hợp lệ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:task="http://www.springframework.org/schema/task"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/task
           https://www.springframework.org/schema/task/spring-task.xsd">

    <!-- Các bean definitions sẽ nằm ở đây. -->
</beans>
```

Namespace `task` chỉ là một prefix được ánh xạ tới URI schema của Spring; bản thân chuỗi `task` không phải tên bean. Nếu thiếu `xmlns:task` hoặc cặp URI/schemaLocation, XML parser có thể báo lỗi schema hoặc prefix không xác định.

### 5.2. Tạo executor bằng <task:executor>

```xml
<task:executor id="workExecutor"
               pool-size="2-4"
               queue-capacity="8"
               rejection-policy="ABORT"
               keep-alive="60"/>
```

Ở đây:

- `id="workExecutor"` là tên bean Spring; cùng tên này có thể được tham chiếu từ `@Qualifier`, `@Async("workExecutor")` hay thuộc tính XML.
- `pool-size="2-4"` đặt core size bằng 2, max size bằng 4. Một giá trị duy nhất như `pool-size="4"` có nghĩa core và max đều bằng 4 (pool cố định về giới hạn worker).
- `queue-capacity="8"` tạo queue lưu tối đa 8 phần tử; `queue-capacity="0"` chọn handoff queue không chứa backlog.
- `rejection-policy="ABORT"`: khi executor quá tải, tác vụ bị từ chối theo abort policy; Spring có thể báo `TaskRejectedException`.
- `keep-alive="60"`: thời gian nhàn rỗi (giây) trước khi non-core workers có thể bị thu hồi.

Cách viết XML này tương đương về các thông số cốt lõi với method `@Bean("workExecutor")` ở mục 3. Phần Java có thêm `threadNamePrefix` tùy chỉnh; ở dạng namespace, Spring sử dụng `id` làm cơ sở đặt prefix cho thread names. Không giả định tên thread sẽ giống hệt giữa hai cách cấu hình.

Ví dụ khác minh họa backpressure từ caller:

```xml
<task:executor id="limitedExecutor"
               pool-size="3-6"
               queue-capacity="20"
               rejection-policy="CALLER_RUNS"/>
```

Khi pool và queue quá tải, `CALLER_RUNS` có thể khiến thread gọi tự thực hiện tác vụ (nếu executor vẫn đang hoạt động). Chính sách này làm caller chậm lại, nhưng có thể gây latency lớn nếu caller là HTTP request worker hoặc event-loop thread. Nó không phù hợp mặc định cho mọi hệ thống. Các chính sách loại bỏ task như `DISCARD` cần được đánh giá cẩn thận để tránh mất nghiệp vụ.

### 5.3. Tạo scheduler bằng <task:scheduler>

```xml
<task:scheduler id="workScheduler" pool-size="2"/>
```

Phần tử này tạo một `ThreadPoolTaskScheduler` có pool size 2. Nếu không khai báo `pool-size`, Spring dùng một thread theo cấu hình namespace mặc định. Không áp `queue-capacity` của `<task:executor>` sang `<task:scheduler>`; đây là hai loại bean khác nhau.

### 5.4. Kích hoạt @Async và @Scheduled qua XML

```xml
<task:annotation-driven
    executor="workExecutor"
    scheduler="workScheduler"/>
```

Ở đây `executor` tham chiếu bean dùng xử lý method `@Async` và `scheduler` tham chiếu bean dùng quản lý `@Scheduled`. Việc khai báo này khác với chỉ tạo executor/scheduler beans: nó **bật xử lý annotation tương ứng**.

Tương đương về mục đích ở Java configuration là sử dụng `@EnableAsync` và/hoặc `@EnableScheduling`, cùng một hay các class `@Configuration` thích hợp. Nếu chỉ có công việc gửi bằng `TaskExecutor.execute(...)`, không bắt buộc bật annotation processing.

Lưu ý: Với Spring proxy mode thường dùng, gọi một method `@Async` từ method khác trên **cùng đối tượng** (`this.asyncMethod()`) không qua proxy, nên không chuyển sang executor như khi gọi từ bên ngoài qua Spring-managed proxy.

### 5.5. Lên lịch hoàn toàn trong XML

Nếu không dùng annotation `@Scheduled`, namespace cũng có thể đăng ký lời gọi định kỳ vào bean:

```xml
<task:scheduler id="reportScheduler" pool-size="2"/>

<task:scheduled-tasks scheduler="reportScheduler">
    <task:scheduled ref="reportService"
                    method="generate"
                    fixed-delay="5000"
                    initial-delay="1000"/>
</task:scheduled-tasks>
```

Đây là **fragment XML**, yêu cầu `reportService` là bean đang có method `generate()` tương thích. `fixed-delay="5000"` tương ứng 5.000 ms sau khi lần trước hoàn thành, `initial-delay="1000"` là 1.000 ms trước lần chạy đầu; cũng có thể khai báo lịch bằng `fixed-rate` hoặc `cron` theo nhu cầu.

Đừng đăng ký *cùng một công việc* hai lần qua cả `@Scheduled` và `<task:scheduled-tasks>` nếu không chủ đích; việc trùng trigger có thể gây xử lý lặp lại.

## 6. XML task namespace khác gì với XML <bean> thông thường?

Ngoài cú pháp rút gọn, có thể khai báo class cụ thể:

```xml
<bean id="workExecutor"
      class="org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor">
    <property name="corePoolSize" value="2"/>
    <property name="maxPoolSize" value="4"/>
    <property name="queueCapacity" value="8"/>
    <property name="threadNamePrefix" value="work-"/>
</bean>
```

Đây là alternative XML **thay thế** `<task:executor id="workExecutor".../>`, không khai báo song song hai bean trùng id trong cùng context.

| Tiêu chí | `@Bean` Java | XML `<task:executor>` | XML `<bean>` |
| --- | --- | --- | --- |
| Ngôn ngữ cấu hình | Java có type checking khi biên dịch | Schema-based XML rút gọn | XML liệt kê class/property |
| Dễ gắn điều kiện/logic | `@Profile`, các conditional configs, Java code | Tùy cấu trúc XML/profile | Tùy cấu trúc XML/profile |
| Tùy chỉnh property đặc thù | Truy cập API setter trực tiếp | Giới hạn vào attributes mà namespace cung cấp | Truy cập bean properties của implementation |
| Tên implementation | Nằm trong mã Java | Được namespace ẩn sau cú pháp | Nằm trong thuộc tính `class` |
| Vòng đời bean | Do Spring container quản lý | Do Spring container quản lý | Do Spring container quản lý |

Với trường hợp cần cấu hình đặc biệt như `taskDecorator` mà `<task:executor>` không biểu diễn trực tiếp, hãy chọn method `@Bean` hoặc XML `<bean>` với những property chính thức được hỗ trợ.

Không kết luận XML là “legacy không chạy nữa”: Spring Framework vẫn hỗ trợ XML bean definitions và `task` namespace; tuy vậy, trong các ứng dụng viết mới, cấu hình Java thường dễ được IDE kiểm tra và refactor hơn.

## 7. Thực nghiệm chạy được: Java config và XML cùng một service

Mục tiêu là **thay cách đăng ký bean nhưng giữ nguyên code nghiệp vụ**. Ví dụ dùng Java 21, Maven và Spring Framework 6.2.1; không yêu cầu Spring Boot. Chương trình có cả một method gửi task trực tiếp vào executor và một method dùng `@Async`.

### 7.1. Cấu trúc

```text
spring-task-config-demo/
├── pom.xml
└── src/main/
    ├── java/demo/TaskConfigDemo.java
    └── resources/task-context.xml
```

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-task-config-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.1</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
        <configuration>
          <mainClass>demo.TaskConfigDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

**Tệp `src/main/java/demo/TaskConfigDemo.java`:**

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

public class TaskConfigDemo {

    public static class WorkService {
        private final TaskExecutor executor;

        public WorkService(TaskExecutor executor) {
            this.executor = executor;
        }

        public CompletableFuture<String> submit(String job) {
            CompletableFuture<String> result = new CompletableFuture<>();
            executor.execute(() -> result.complete("processed:" + job));
            return result;
        }

        @Async("workExecutor")
        public CompletableFuture<String> asyncHandle(String job) {
            return CompletableFuture.completedFuture("async:" + job);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class JavaConfig {
        @Bean("workExecutor")
        public ThreadPoolTaskExecutor workExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(4);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("work-");
            return executor;
        }

        @Bean("workScheduler")
        public ThreadPoolTaskScheduler workScheduler() {
            ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
            scheduler.setPoolSize(2);
            scheduler.setThreadNamePrefix("schedule-");
            return scheduler;
        }

        @Bean("workService")
        public WorkService workService(
                @Qualifier("workExecutor") TaskExecutor executor) {
            return new WorkService(executor);
        }
    }

    public static void main(String[] args) throws Exception {
        boolean xml = args.length > 0 && "xml".equals(args[0]);
        String mode = xml ? "xml" : "java";

        try (ConfigurableApplicationContext context = xml
                ? new ClassPathXmlApplicationContext("task-context.xml")
                : new AnnotationConfigApplicationContext(JavaConfig.class)) {
            WorkService service =
                    context.getBean("workService", WorkService.class);

            String result = service.submit("J1")
                    .get(5, TimeUnit.SECONDS);
            String asyncResult = service.asyncHandle("J2")
                    .get(5, TimeUnit.SECONDS);

            System.out.println("mode=" + mode);
            System.out.println("execute=" + result);
            System.out.println("annotation=" + asyncResult);
            System.out.println("executor=" + context.getBean("workExecutor")
                    .getClass().getSimpleName());
            System.out.println("scheduler=" + context.getBean("workScheduler")
                    .getClass().getSimpleName());
        }
    }
}
```

Service có hai đường sử dụng executor: `submit()` gọi `execute()` trực tiếp; `asyncHandle()` dùng annotation và được Spring proxy chuyển sang executor. Khối `main` nhận cùng một interface làm việc bất kể chọn context XML hay Java.

**Tệp `src/main/resources/task-context.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:task="http://www.springframework.org/schema/task"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/task
           https://www.springframework.org/schema/task/spring-task.xsd">

    <task:executor id="workExecutor"
                   pool-size="2-4"
                   queue-capacity="8"
                   rejection-policy="ABORT"
                   keep-alive="60"/>
    <task:scheduler id="workScheduler" pool-size="2"/>
    <task:annotation-driven
            executor="workExecutor" scheduler="workScheduler"/>

    <bean id="workService" class="demo.TaskConfigDemo$WorkService">
        <constructor-arg ref="workExecutor"/>
    </bean>
</beans>
```

Dấu `$` trong `class="demo.TaskConfigDemo$WorkService"` là cú pháp tên **nested static class** trong JVM; không thay bằng dấu chấm ở chuỗi class XML này. Bean `workService` được tạo qua constructor có tham số `TaskExecutor`, đúng như cách Java config đã tạo.

### 7.2. Chạy bằng Java configuration

Trong thư mục gốc dự án:

```bash
mvn -q -DskipTests compile exec:java
```

**Output chuẩn của chương trình** (không tính thông báo từ Maven/JVM nếu môi trường có thêm log):

```text
mode=java
execute=processed:J1
annotation=async:J2
executor=ThreadPoolTaskExecutor
scheduler=ThreadPoolTaskScheduler
```

Chương trình đã được kiểm chứng bằng Maven và trình biên dịch với `maven.compiler.release=21`.

### 7.3. Chạy bằng XML task namespace

Vẫn giữ nguyên source code service, chỉ truyền một đối số:

```bash
mvn -q -Dexec.args=xml exec:java
```

**Output chuẩn của chương trình:**

```text
mode=xml
execute=processed:J1
annotation=async:J2
executor=ThreadPoolTaskExecutor
scheduler=ThreadPoolTaskScheduler
```

Bản XML cũng đã được chạy kiểm chứng. Tùy phiên bản Spring và cách khởi tạo infrastructure beans, log ứng dụng **có thể xuất hiện cảnh báo BeanPostProcessorChecker** trong lúc đăng ký processor cho `@Async`/`@Scheduled`; ví dụ kiểm chứng với Spring 6.2.1 đã có cảnh báo đó, nhưng các bean vẫn được tạo và tác vụ hoàn thành. Khi vận hành, cần phân biệt warning lúc tạo context với lỗi cấu hình hoặc lỗi thực thi thật sự; không tự giả định mọi warning đều vô hại trong mọi dự án.

Nếu muốn dùng scheduler bean để chạy `@Scheduled` trong **nhánh Java**, cần bổ sung `@EnableScheduling` vào configuration; ở ví dụ này nhánh Java chỉ bật `@EnableAsync` vì không có method `@Scheduled`. Nhánh XML có `<task:annotation-driven executor=... scheduler=.../>` để minh họa cả hai khả năng.

### 7.4. Những gì ví dụ chứng minh

- Java `@Bean` và XML `task` namespace đều đăng ký executor/scheduler theo tên bean thống nhất.
- `WorkService` không biết bean được định nghĩa bằng ngôn ngữ cấu hình nào.
- `@Async("workExecutor")` hoạt động khi annotation processing đã được kích hoạt và method được gọi thông qua Spring-managed proxy.
- `CompletableFuture.get(timeout)` giúp chương trình chờ có giới hạn và kiểm tra kết quả trước khi đóng ApplicationContext.
- Cấu hình executor chỉ giải quyết việc nhận và chạy task trong tiến trình hiện tại; không tự tạo hàng đợi bền vững hoặc đảm bảo task hoàn thành khi process chết.

## 8. Kết nối service qua interface và tên bean

Nếu có nhiều executors, Spring phải biết service nào sử dụng pool nào. Với Java configuration, có thể khai báo:

```java
@Bean
public ExportService exportService(
        @Qualifier("workExecutor") TaskExecutor executor) {
    return new ExportService(executor);
}
```

Đây là fragment; `ExportService` là một service bất kỳ có constructor nhận `TaskExecutor`. Phần `@Qualifier("workExecutor")` chọn bean theo vai trò, không ép kiểu phụ thuộc vào `ThreadPoolTaskExecutor`.

Bản XML có thể truyền dependency bằng constructor:

```xml
<bean id="exportService" class="demo.ExportService">
    <constructor-arg ref="workExecutor"/>
</bean>
```

Lưu ý phải có class `demo.ExportService` trong ứng dụng nếu dùng fragment này; nó chỉ minh họa wiring. Với chỉ một bean phù hợp kiểu `TaskExecutor`, Spring có thể tự chọn; khi có nhiều bean, qualifier/tên rõ ràng giúp tránh ambiguity hoặc vô tình sử dụng pool mặc định.

Một service được viết tốt chỉ gọi `executor.execute(task)` khi cần gửi việc; nó không cần biết `pool-size`, `queue-capacity` hay XML schema. Những cấu hình này thuộc infrastructure.

## 9. @Async, @Scheduled và khác biệt giữa định nghĩa bean với kích hoạt annotation

Có ba thao tác khác nhau:

1. **Đăng ký implementation:** tạo bean `ThreadPoolTaskExecutor` hoặc `ThreadPoolTaskScheduler`.
2. **Đăng ký xử lý annotation:** dùng `@EnableAsync` / `@EnableScheduling` hoặc `<task:annotation-driven>`.
3. **Gắn method với cơ chế:** đặt `@Async` / `@Scheduled` đúng chỗ, hoặc đăng ký `<task:scheduled-tasks>` nếu muốn cấu hình lịch bằng XML.

Thiếu (1), tác vụ có thể dùng executor mặc định/fallback hoặc không đúng giới hạn mong muốn. Thiếu (2), method mang annotation không nhất thiết được xử lý như kỳ vọng. Thiếu (3), bean executor có thể được tạo nhưng không ai gửi công việc cho nó.

### 9.1. Chọn đúng executor cho @Async

Trong Java:

```java
@Async("workExecutor")
public CompletableFuture<String> generatePreview() {
    // Đoạn minh họa method trên Spring-managed bean.
    return CompletableFuture.completedFuture("done");
}
```

Method cần được gọi từ client đi qua Spring proxy. Việc đặt tên trong `@Async("workExecutor")` giúp rõ bean được dùng. Trong XML, cũng có thể đặt `executor="workExecutor"` trên `<task:annotation-driven>` để chọn executor mặc định cho annotation không ghi tên cụ thể.

Một lỗi phổ biến là nghĩ `@Async` tự biến JDBC/HTTP blocking thành nonblocking I/O: lời gọi blocking vẫn chiếm worker của executor trong khoảng chờ; thay đổi chỉ chuyển điểm chặn sang thread khác.

### 9.2. Chọn scheduler cho @Scheduled

Scheduler quyết định lịch kích hoạt; nó cũng có pool size và lifecycle. Nếu có quá nhiều job chậm trên scheduler một thread, các lần chạy khác có thể bị trì hoãn. Không dùng scheduler bean chỉ để chạy một `Runnable` một lần như executor thông thường trừ khi thiết kế thực sự cần một thời điểm kích hoạt.

Cần nhớ rằng trong hệ thống nhiều instance, mỗi instance có ApplicationContext và có thể có lịch chạy riêng. Nếu nghiệp vụ chỉ muốn một instance thực hiện, cần coordination hoặc distributed locking phù hợp; XML/annotation đơn lẻ không cung cấp leader election.

## 10. Quản trị cấu hình theo môi trường

### 10.1. Java @Profile

Có thể thay bean theo profile:

```java
@Bean("workExecutor")
@Profile("dev")
public TaskExecutor developmentExecutor() {
    return new SyncTaskExecutor();
}

@Bean("workExecutor")
@Profile("!dev")
public ThreadPoolTaskExecutor productionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    return executor;
}
```

Đây là fragment cần imports `@Profile`, `TaskExecutor`, `SyncTaskExecutor`, `ThreadPoolTaskExecutor` và chứa trong lớp cấu hình. Hai method tạo cùng tên bean nhưng chỉ một profile branch nên được kích hoạt trong một context theo điều kiện. Lưu ý `SyncTaskExecutor` chạy công việc **ngay trên thread gọi**, nên hành vi timing khác hoàn toàn. Không nên mặc định test đồng bộ mô phỏng đầy đủ race conditions của production.

### 10.2. XML profile

XML cho phép dùng `profile` trong cấu trúc bean definitions, nhưng phải tôn trọng quy tắc schema, phạm vi context và đặt tên bean không trùng khi profile khác nhau. Ví dụ một fragment mô tả bean theo môi trường:

```xml
<beans profile="dev">
    <bean id="workExecutor"
          class="org.springframework.core.task.SyncTaskExecutor"/>
</beans>
<beans profile="prod">
    <task:executor id="workExecutor"
                   pool-size="4-8"
                   queue-capacity="100"/>
</beans>
```

Đây là **fragment đặt bên trong root `<beans>` phù hợp**, không phải một XML file hoàn chỉnh. Nếu muốn dùng `<task:executor>` trong nested `<beans>`, cần xác nhận schema và version cho phép cách cấu trúc đó. Cũng có thể tách nhiều XML config files rồi chọn file cần import theo môi trường. Luôn kiểm tra thực tế bean nào có trong context sau khi profile được bật.

### 10.3. Phân biệt Spring Framework và Spring Boot

Spring Boot có các cơ chế **auto-configuration** và properties như `spring.task.execution.pool.core-size`, `spring.task.execution.pool.max-size` và `spring.task.execution.pool.queue-capacity` theo phiên bản Boot. Các properties này chỉ áp dụng khi auto-configured executor tương ứng đang được sử dụng; không nên giả định một `@Bean("workExecutor")` do ứng dụng tự tạo sẽ tự nhận cấu hình pool từ Boot.

Nếu ứng dụng chỉ dùng Spring Framework, các method `@Bean` và XML `task` namespace ở trên hoạt động mà **không cần** Spring Boot hay `application.properties`. Tập trung vào các bean thực sự được tạo trong ApplicationContext.

## 11. Lưu ý về lỗi cấu hình, quá tải và vận hành

### 11.1. Tên bean và ambiguity

Đặt tên bean rõ chức năng: `emailExecutor`, `reportExecutor`, `scheduledJobs`. Đừng đặt tên chung như `executor` rồi tạo nhiều bean cùng kiểu mà không xác định injection point. Trùng bean name giữa Java configuration và XML nhập vào cùng một context có thể gây conflict, bị override hoặc bị chặn tùy thiết lập; tránh khai báo lặp cùng tên khi cả hai đường cấu hình cùng được load.

### 11.2. Quá tải, queue và rejection

`ThreadPoolTaskExecutor` có pool và queue giới hạn riêng. Khi queue và worker đều bận, mặc định tác vụ có thể bị từ chối (Spring biểu diễn bằng `TaskRejectedException`). Một `execute()` trả về bình thường không bảo đảm nội dung task đã xử lý thành công; với bất đồng bộ, exception bên trong worker có đường quan sát riêng.

`rejection-policy="CALLER_RUNS"` là một lựa chọn điều tiết, nhưng có thể làm thread gọi chặn dài; nếu request server đang dùng event loop hoặc bị giới hạn số worker, cần đánh giá trước khi dùng. Các policy discard có thể đánh mất việc và không phù hợp với tác vụ bắt buộc hoàn tất.

### 11.3. Timeout và context propagation

Tác vụ chạy ở thread khác có thể không mang theo ThreadLocal, MDC, security context hoặc transaction context từ thread gọi. Cần truyền input cần thiết rõ ràng; dùng task decorator hoặc cơ chế propagation phù hợp nếu muốn mang theo metadata quan sát.

Nếu task phụ thuộc database/network, cấu hình timeout tại client/dependency, kiểm tra connection pool và theo dõi queue wait; tăng threads/queue không thay thế tối ưu bottleneck. Khi method `@Async` trả về `Future`, cần thu nhận exception hoặc xử lý kết quả đúng cách. Với method `void`, lỗi không tự được trả về caller.

### 11.4. Shutdown và môi trường chạy

Khi context đóng, threads và tasks đang chạy chịu chính sách shutdown của từng implementation. Kiểm tra cài đặt await termination, accept-after-close và phương án không mất tác vụ quan trọng. Không nên dùng in-memory executor như hệ thống hàng đợi bền vững cho nghiệp vụ cần replay sau restart.

### 11.5. Kiểm chứng thực tế

Sau khi chọn cách cấu hình, hãy kiểm tra:

- Bean có tên và kiểu đúng trong ApplicationContext; không bị hai nhánh Java/XML cùng định nghĩa.
- `corePoolSize`, `maxPoolSize`, `queueCapacity`, số scheduler workers và thread name prefix thực sự khớp mong đợi.
- Method `@Async`/`@Scheduled` đã kích hoạt annotation processing và lời gọi đi đúng qua proxy.
- Dưới tải, quan sát `activeCount`, `queueSize`, rejection, throughput, task execution time, p95/p99 wait time và memory.
- Bảo đảm dừng context không bỏ mặc threads và không giả định công việc trong queue là durable.

## 12. Các lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách kiểm tra/sửa |
| --- | --- | --- |
| Chỉ có `@Bean executor` nhưng kỳ vọng `@Async` chạy | Annotation không được xử lý như mong muốn | Bật `@EnableAsync` hoặc `<task:annotation-driven>` và gọi qua proxy |
| Chỉ tạo scheduler rồi kỳ vọng `@Scheduled` hoạt động | Job không được đăng ký theo annotation | Bật `@EnableScheduling` hoặc XML annotation-driven |
| Viết XML thiếu namespace/schema | Context không parse được | Kiểm tra `xmlns:task` và cặp `schemaLocation` |
| Viết `pool-size="2-4"` nhưng hiểu là luôn có 4 workers | Sai ước lượng concurrency | Phân biệt core/max; chú ý queue-capacity |
| Để queue rất lớn và chỉ tăng maxPoolSize | Task chờ lâu, pool hiếm khi mở rộng | Đo queue wait và cân chỉnh cùng core, max, queue |
| Nhập cả Java config và XML có bean trùng id | Xung đột/ghi đè definition | Chọn đường cấu hình rõ ràng, kiểm tra bean registry |
| `@Async` self-invocation trong cùng bean | Không đi qua proxy mặc định | Gọi từ Spring-managed client khác |
| Dùng `TaskExecutor` cho scheduling | Thiếu semantics thời gian kích hoạt | Dùng `TaskScheduler` và `@Scheduled`/scheduled-tasks |
| Tự tạo executor bằng `new` trong service rồi quên shutdown | Rò rỉ threads/tài nguyên | Đưa executor thành Spring-managed bean |
| Coi task đã submit là task đã thành công | Bỏ sót worker exception | Dùng Future/CompletionStage, quan sát error/rejection |
| Tin XML namespace tự áp dụng mọi feature của implementation | Mất các tùy chỉnh đặc thù | Dùng `@Bean` hoặc `<bean>` cho property không được namespace hỗ trợ |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Có `ThreadPoolTaskExecutor` bean tên `workExecutor`, nhưng method `@Async("workExecutor")` chạy đồng bộ khi gọi từ cùng bean. Điều gì cần kiểm tra?

Hãy kiểm tra `@EnableAsync`/`<task:annotation-driven>` đã có chưa; đặc biệt kiểm tra lời gọi có đang đi qua `this.method()` và bỏ qua Spring proxy hay không. Kiểm tra tiếp loại executor được tiêm và có dùng `SyncTaskExecutor` không.

**Câu 2.** XML `<task:executor pool-size="3-9" queue-capacity="100">` có tự tạo 9 thread ngay khi khởi động không?

Không. Nó cấu hình core/max worker và queue capacity; core threads thường được tạo dần khi có task, và pool chỉ mở rộng ngoài core khi queue không nhận thêm. Cần chạy tải và quan sát thực tế.

**Câu 3.** Ứng dụng vừa có `@Bean("workExecutor")` vừa import XML khai báo `<task:executor id="workExecutor">`. Có nên giữ cả hai không?

Không nên khai báo hai nguồn chủ sở hữu cùng một bean name trong một ApplicationContext, trừ khi có cơ chế override được thiết kế rõ ràng. Chọn một nguồn cấu hình hoặc tổ chức các profile/files để mỗi context chỉ có một definition hiệu lực.

**Câu 4.** Có thể thay `ThreadPoolTaskExecutor` bằng `SyncTaskExecutor` trong test mà không sửa service không?

Có, nếu service phụ thuộc interface `TaskExecutor`. Tuy nhiên test synchronous chỉ kiểm chứng logic gửi và thực hiện theo thứ tự; concurrency issues thực tế vẫn cần test riêng.

**Câu 5.** Tại sao trong XML ví dụ có cả `<task:scheduler>` lẫn `<task:annotation-driven scheduler="...">`?

Phần tử thứ nhất **tạo tài nguyên scheduler**; phần tử thứ hai **đăng ký cơ chế dùng scheduler đó để xử lý annotation**. Cần tách rõ tạo bean và kích hoạt tính năng.

## 14. Tóm tắt thực hành

- **Java configuration:** dùng `@Bean` để tạo `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler`; bật `@EnableAsync` và/hoặc `@EnableScheduling` khi dùng annotation.
- **XML task namespace:** `<task:executor>`, `<task:scheduler>` định nghĩa tài nguyên; `<task:annotation-driven>` kích hoạt xử lý `@Async`/`@Scheduled`; `<task:scheduled-tasks>` có thể khai báo lịch mà không cần annotation.
- **DI bằng interface:** business service phụ thuộc `TaskExecutor`/`TaskScheduler`, để Java config hay XML quyết định implementation, sizing và lifecycle.
- **Không bỏ qua vận hành:** thread pool size, queue-capacity, policy từ chối, shutdown, trạng thái proxy và monitoring phải được xác minh trên bean thực tế.

### Tài liệu tham khảo

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework 6.2 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2 — ThreadPoolTaskScheduler API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Spring Framework 6.2 — @EnableAsync API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)