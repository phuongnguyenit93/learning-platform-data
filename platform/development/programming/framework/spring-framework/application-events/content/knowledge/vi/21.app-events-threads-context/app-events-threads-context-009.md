# Đóng executor đúng lifecycle trong Spring Application Events

## 1. Tại sao vòng đời executor quan trọng?

Trong một ứng dụng Spring, `@Async` hoặc một `TaskExecutor` giúp chuyển công việc từ publisher thread sang worker thread. Với Spring Application Events, điều này thường dùng để gửi email, cập nhật projection, ghi audit phụ trợ hoặc xử lý thông báo sau khi có một domain event.

Nhưng **executor là một tài nguyên có vòng đời**: nó tạo/giữ thread, nhận task, lưu task trong queue, cho worker thực thi và cuối cùng phải ngừng nhận việc rồi thu hồi tài nguyên. Nếu bỏ qua quá trình đóng, ứng dụng có thể:

- Kết thúc HTTP server nhưng thread pool vẫn sống và làm JVM không thoát.
- Mất những task còn trong queue khi tiến trình bị dừng.
- Ngắt một task đang ghi dữ liệu khiến trạng thái trở nên khó xác định.
- Tiếp tục chạy listener sau khi `DataSource`, HTTP client hoặc bean phụ thuộc đã bị destroy.
- Từ chối task được submit trong lúc shutdown nhưng không có log/metric thích hợp.
- Kéo dài rolling deployment vượt thời hạn graceful shutdown của nền tảng.
- Vô tình tạo nhiều executor bằng `Executors.newFixedThreadPool(...)` mà không ai chịu trách nhiệm đóng.

**Mục tiêu:** executor chỉ chạy khi ứng dụng cho phép nhận công việc; khi `ApplicationContext` đóng, executor xử lý những task đang chạy/đang chờ theo một **chính sách rõ ràng**, có timeout, có quan sát, và không giả định công việc đã hoàn tất chỉ vì đã gọi `close()`.

Bài này thuộc nhóm **Thread và context** trong Spring Framework Application Events. Trọng tâm là quản lý executor phục vụ listener, không phải cách tạo thread Java nói chung.

### Một đường xử lý thường gặp

~~~text
HTTP / Scheduler / Consumer
             |
             v
     Publisher.publishEvent(event)
             |
             v
       @Async @EventListener
             |
             v
      Spring-managed TaskExecutor
             |
        +----+-----+
        |          |
       RUNNING     QUEUED
        |          |
        +----+-----+
             |
     ApplicationContext.close()
             |
     chính sách shutdown:
     - có tiếp nhận task mới?
     - chờ task đang chạy?
     - xử lý queue hay loại bỏ?
     - tối đa chờ bao lâu?
             |
             v
       Executor stopped
~~~

## 2. Ai sở hữu executor và ai chịu trách nhiệm đóng?

Một quy tắc hữu ích: **thành phần tạo và sở hữu executor phải chịu trách nhiệm quản lý vòng đời của nó**.

| Cách tạo executor | Ai sở hữu | Cách đóng thường phù hợp |
| --- | --- | --- |
| `@Bean ThreadPoolTaskExecutor` | Spring `ApplicationContext` | Để Spring khởi tạo và gọi destruction callback |
| `@Bean(destroyMethod = "shutdown") ExecutorService` | Spring quản lý bean, thư viện JDK cung cấp pool | Spring gọi `shutdown()`; bổ sung policy chờ nếu cần |
| `new ThreadPoolExecutor(...)` trong một service | Service tự quản lý | Service phải đóng ở lifecycle hook, hoặc chuyển thành bean Spring |
| Executor do application server/Jakarta EE cung cấp | Container bên ngoài | Tuân thủ hợp đồng container, không tùy tiện shutdown tài nguyên không thuộc mình |
| `SimpleAsyncTaskExecutor` | Tùy bean/config | Không phải thread pool tái sử dụng; cần hiểu riêng concurrency/shutdown |
| Executor do Spring Boot auto-config | Spring Boot/Spring | Cấu hình qua các property/bean phù hợp, xác minh executor thực tế đang được sử dụng |

Cách khuyến nghị cho bài toán này: **khai báo `ThreadPoolTaskExecutor` làm Spring bean, dùng tên rõ ràng, và để context quản lý init/destroy**. Không tạo một pool mới trong mỗi lần xử lý event.

### Ví dụ cấu hình bean

~~~java
@Configuration
@EnableAsync
public class EventExecutorConfiguration {

    @Bean("eventsExecutor")
    public ThreadPoolTaskExecutor eventsExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("events-");

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
~~~

Đây là **mã minh họa trong một ứng dụng Spring**; cần import `Configuration`, `EnableAsync`, `Bean`, `ThreadPoolTaskExecutor`. Khi bean thuộc ApplicationContext, Spring quản lý callback khởi tạo/hủy của `ThreadPoolTaskExecutor`. Vì vậy **không cần tự gọi `executor.initialize()` trong phương thức `@Bean` và cũng không gọi `shutdown()` từ một listener nghiệp vụ**.

Con số pool size, queue capacity và thời gian chờ là giá trị minh họa, không phải cấu hình mặc định nên áp dụng cho mọi workload.

## 3. Hiểu lifecycle của ApplicationContext và executor

Với `ConfigurableApplicationContext.close()`, Spring thực hiện quá trình đóng context, bao gồm phát `ContextClosedEvent`, điều phối lifecycle processor và hủy các singleton phù hợp. `ThreadPoolTaskExecutor` là bean có hỗ trợ quản lý lifecycle/shutdown, nên có thể tham gia quá trình này.

Diễn giải ở mức khái niệm:

~~~text
ApplicationContext hoạt động
      |
      | ContextClosedEvent bắt đầu quá trình đóng
      v
Lifecycle stop / early shutdown signaling
      |
      | các bean được stop theo phase/policy
      v
Destroy singleton beans
      |
      | ThreadPoolTaskExecutor.destroy() / shutdown()
      v
Close hoàn tất
~~~

**Đừng hiểu sơ đồ thành trình tự cứng áp dụng cho mọi bean.** Chính sách khác nhau (đặc biệt `waitForTasksToCompleteOnShutdown`, `acceptTasksAfterContextClose` và `strictEarlyShutdown`) có thể thay đổi việc executor dừng sớm, tiếp nhận task muộn và có tham gia coordinated lifecycle stop hay không.

### 3.1. Close không đồng nghĩa mọi công việc hoàn thành

Khi gọi `context.close()`:

- Spring gọi các hook stop/destroy của bean theo policy.
- Executor có thể chờ task đang chạy, xử lý task trong queue hoặc ngắt/hủy task tùy cấu hình.
- Một khoảng `awaitTerminationSeconds` chỉ là **thời gian chờ tối đa**, không phải lời hứa rằng tất cả task đều thành công.
- Nếu một task không tôn trọng interrupt hoặc bị treo ở I/O, shutdown có thể không hoàn tất sạch trong giới hạn.
- Kể cả task đã hoàn thành trong JVM, delivery sang hệ thống khác vẫn có thể chưa bền vững nếu không có cơ chế xác nhận phù hợp.

Từ “graceful shutdown” phải được định nghĩa cụ thể: **ngừng nhận việc mới, cho việc đang chạy hoàn tất, chờ có giới hạn, rồi thực thi policy cho việc chưa xong**.

### 3.2. ContextClosedEvent không phải lệnh đóng pool tùy tiện

Một listener nhận `ContextClosedEvent` có thể ghi log hoặc cập nhật trạng thái, nhưng không nên tự gọi `shutdown()` lên một shared executor do Spring quản lý nếu các bean khác còn phụ thuộc vào pool đó. Spring đã có lifecycle cho bean executor.

Đặc biệt tránh thiết kế “khi đóng context, publish một async event dọn dẹp rồi tin rằng listener sẽ luôn chạy”: executor có thể đang nhận tín hiệu dừng; task có thể bị từ chối, hủy hoặc không còn đủ thời gian trước khi process kết thúc.

## 4. Ba cấu hình quan trọng trong Spring Framework 6.2

Spring cung cấp các property rõ nghĩa ở `ExecutorConfigurationSupport`, lớp cơ sở của `ThreadPoolTaskExecutor`.

### 4.1. setWaitForTasksToCompleteOnShutdown(true)

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
~~~

Policy này yêu cầu executor thực hiện shutdown có chủ đích, cho **task đang chạy tiếp tục** và **task còn trong queue có cơ hội được thực thi**, thay vì đơn giản cố ngắt các task đang chạy và xóa queue ngay tại bước destroy.

Chi tiết quan trọng theo Spring Framework 6.2:

- Mặc định của property này là `false`.
- Khi `true`, executor ưu tiên shutdown mềm tại **bước destruction** và **bỏ qua coordinated lifecycle stop** thông thường.
- Điều đó có thể dẫn đến việc task vẫn được submit trong một phần giai đoạn context đóng, thay vì bị từ chối ngay khi `ContextClosedEvent` xuất hiện.
- Khi `false`, Spring có cơ chế coordinated lifecycle stop và policy shutdown mặc định riêng. Đừng khẳng định mọi task đều bị cắt ngay khi phát `ContextClosedEvent`, bởi executor có thể hoàn tất task hiện tại trong giai đoạn coordinated stop.

**Lựa chọn `true` có trade-off:** phù hợp nếu muốn drain queue trong bước destroy, nhưng **không phải** chế độ nghiêm ngặt ngừng nhận task ngay ở đầu shutdown. Cần hiểu điều này khi có nhiều producer còn chạy.

### 4.2. setAwaitTerminationSeconds(n)

~~~java
executor.setAwaitTerminationSeconds(30);
~~~

Đặt thời gian **tối đa** mà shutdown sẽ block để chờ executor kết thúc trước khi container tiếp tục đóng các tài nguyên còn lại. Ví dụ 30 giây chỉ là budget cho việc chờ, không đảm bảo task nào cũng hoàn thành hay thành công.

Nếu đặt `waitForTasksToCompleteOnShutdown(true)` nhưng **không** đặt await-termination, task có thể tiếp tục trong khi Spring đang destroy các bean khác mà nó dùng. Vì vậy cặp cấu hình thường có ý nghĩa:

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(30);
~~~

Một ví dụ rủi ro: worker cần `DataSource` để commit khi pool đã bắt đầu shutdown; nếu container đóng `DataSource` trước khi worker xong, task có thể lỗi. Await-termination giúp giảm rủi ro bằng cách đợi ở destruction step, nhưng **còn phụ thuộc thứ tự lifecycle, thời hạn và các task có kết thúc được hay không**.

Nếu budget hết mà task chưa xong, hệ thống vẫn cần log/metric và chiến lược phục hồi. Tránh diễn đạt `awaitTerminationSeconds(30)` như cơ chế “chắc chắn không mất task”.

### 4.3. setStrictEarlyShutdown(true)

~~~java
executor.setStrictEarlyShutdown(true);
~~~

Ở Spring Framework 6.2, property này yêu cầu `ThreadPoolTaskExecutor` phát tín hiệu shutdown **sớm lúc context bắt đầu đóng**, không tiếp nhận task mới sau điểm đó theo policy tương ứng. Giá trị mặc định của `ThreadPoolTaskExecutor` trong 6.2 là `false`, cho phép mô hình lenient late task submission cùng coordinated lifecycle stop.

Điểm dễ nhầm: các property `setWaitForTasksToCompleteOnShutdown(true)` và `setAcceptTasksAfterContextClose(true)` có thể **override** hiệu ứng early shutdown nghiêm ngặt. Do đó không nên thiết lập cả ba flag rồi mặc định tin rằng strict early stop vẫn đang chi phối.

### 4.4. setAcceptTasksAfterContextClose(true)

~~~java
executor.setAcceptTasksAfterContextClose(true);
~~~

Khi đặt `true`, executor được phép tiếp nhận task muộn trong giai đoạn context close, nhưng có thể bỏ qua coordinated stop. Đây là một lựa chọn có điều kiện, không phải lời khuyên chung. Nó phù hợp chỉ khi những bean trong shutdown callback thật sự cần submit thêm task và bạn có chính sách chờ/destroy đủ an toàn.

**Mức quan trọng nhất:** đọc Javadoc đúng **phiên bản Spring đang dùng**. Hành vi về early shutdown của `ThreadPoolTaskExecutor` đã được điều chỉnh trong các bản Spring 6.1+, nên các bài hướng dẫn cũ có thể mô tả mặc định khác.

## 5. Chọn chính sách shutdown theo loại công việc

Không có một bộ flag phù hợp cho mọi listener:

| Nhu cầu | Hướng chọn | Điều phải kiểm tra |
| --- | --- | --- |
| Task phụ, có thể bỏ dở khi stop | Coordinated lifecycle mặc định hoặc stop chủ động | Có log/metric cho việc bị hủy |
| Muốn chặn task mới ngay khi close | Xem xét `strictEarlyShutdown(true)` (khi không bị flag khác override) | Producer còn submit muộn không? Task bị reject xử lý thế nào? |
| Muốn thực thi cả task đang queue khi destroy | `waitForTasksToCompleteOnShutdown(true)` | Queue có backlog lớn không? Có chấp nhận late task không? |
| Muốn chờ task trước khi destroy dependency khác | `awaitTerminationSeconds(...)` cùng policy phù hợp | Budget có đủ và có bao giờ bị treo không? |
| Task cuối shutdown do component khác submit | Cân nhắc lifecycle order/phase và `acceptTasksAfterContextClose` nếu thật sự cần | Có bỏ qua coordinated lifecycle stop không? |
| Công việc phải được thực hiện dù process crash | Lưu job/outbox bền vững + dispatcher | Shutdown trong RAM không đủ |
| Nhiều service cần graceful stop riêng | `SmartLifecycle`/orchestrator hoặc job framework | Thứ tự stop, completion callback, timeout |

**Một bài toán kiến trúc khác với đóng pool:** ngừng **producer** tạo task mới trước, chờ/hoàn tất consumer, rồi mới đóng dependency. Chỉ đặt timeout cho executor nhưng vẫn để controller, queue consumer hoặc scheduler liên tục đẩy việc vào pool có thể khiến shutdown khó hội tụ.

### 5.1. Capacity và bounded queue

~~~java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(200);
~~~

Capacity là phần của chính sách shutdown. Với backlog lớn, việc drain queue có thể lâu hơn thời gian dành cho pod. Queue không giới hạn là một rủi ro vì nó che giấu overload và kéo dài drain; queue quá nhỏ thì dễ từ chối task khi burst. Cần đo throughput, thời gian tác vụ, thời gian shutdown có thể chấp nhận và lưu lượng cao nhất.

### 5.2. Rejection là đường lỗi riêng

Khi pool không nhận thêm task, executor có thể ném `TaskRejectedException`/`RejectedExecutionException` hoặc áp dụng policy từ chối khác theo cấu hình. Không mặc định exception của **task body** và lỗi **submit task** đi chung một error handler.

Nếu listener xử lý event qua `@Async`, một task có thể bị từ chối **ngay ở đường scheduling**, trong khi exception xảy ra sau khi task đã bắt đầu được xử lý ở worker. Theo dõi hai loại lỗi riêng.

## 6. Ví dụ đầy đủ Java 17+: context đóng và chờ @Async listener hoàn thành

Đây là một chương trình Spring Framework **6.2.8** chạy được với Java 17+ và Maven, **không cần Spring Boot**. Nó minh họa:

- `ThreadPoolTaskExecutor` là **Spring bean** và không được tự shutdown thủ công.
- `@EnableAsync` kích hoạt annotation `@Async("eventsExecutor")` trên listener.
- Listener nhận `WorkRequested` qua `@EventListener` và chạy trên executor.
- Hai `CountDownLatch` xác định thứ tự log mà không dùng `Thread.sleep(...)`.
- Khi rời `try-with-resources`, `AnnotationConfigApplicationContext.close()` đóng context; policy configured cho executor chờ task trước khi close hoàn tất.
- Không thử tạo thêm task lúc shutdown, nên tránh gán giả định về thứ tự dispatch các listener đóng context.

### 6.1. Cấu trúc thư mục

~~~text
executor-lifecycle-demo/
├── pom.xml
└── src/main/java/ExecutorLifecycleDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>executor-lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>ExecutorLifecycleDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. ExecutorLifecycleDemo.java

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class ExecutorLifecycleDemo {

    private static final CountDownLatch WORKER_STARTED =
        new CountDownLatch(1);
    private static final CountDownLatch ALLOW_COMPLETION =
        new CountDownLatch(1);

    public record WorkRequested(String jobId) { }

    // Class listener không final để Spring tạo proxy khi cần.
    public static class WorkListener {

        @Async("eventsExecutor")
        @EventListener
        public void onWorkRequested(WorkRequested event) {
            System.out.println(
                "WORK_STARTED " + event.jobId()
            );
            WORKER_STARTED.countDown();

            try {
                if (!ALLOW_COMPLETION.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("worker gate timeout");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("worker interrupted", ex);
            }

            System.out.println(
                "WORK_DONE " + event.jobId()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {

        @Bean("eventsExecutor")
        public ThreadPoolTaskExecutor eventsExecutor() {
            ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("events-");

            // Drain đang chạy và các task đã queue khi shutdown.
            executor.setWaitForTasksToCompleteOnShutdown(true);

            // Tối đa 10 giây để chờ ở bước destruction.
            executor.setAwaitTerminationSeconds(10);
            return executor; // Spring tự quản lý init/destroy.
        }

        @Bean
        public WorkListener workListener() {
            return new WorkListener();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("PUBLISH");
            context.publishEvent(new WorkRequested("job-1"));

            if (!WORKER_STARTED.await(10, TimeUnit.SECONDS)) {
                ALLOW_COMPLETION.countDown();
                throw new IllegalStateException("worker did not start");
            }

            // Worker đã chạy nhưng đang đợi latch thứ hai.
            System.out.println("PUBLISH_RETURNED");
            ALLOW_COMPLETION.countDown();
        }

        // try-with-resources đã gọi context.close().
        System.out.println("CONTEXT_CLOSED");
    }
}
~~~

Chạy từ thư mục `executor-lifecycle-demo` bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

Các dòng **do chương trình tự in ra** khi không xảy ra timeout, không tính thông báo Maven:

~~~text
PUBLISH
WORK_STARTED job-1
PUBLISH_RETURNED
WORK_DONE job-1
CONTEXT_CLOSED
~~~

### 6.4. Phân tích thứ tự

1. `main` in `PUBLISH` và phát event. `@EventListener` được Spring đăng ký, còn `@Async("eventsExecutor")` chuyển việc thực thi phương thức listener cho bean executor.
2. Worker in `WORK_STARTED`, rồi giảm latch `WORKER_STARTED`. Vì main đợi latch, `PUBLISH_RETURNED` chỉ được in **sau khi** worker đã in `WORK_STARTED`.
3. Worker bị giữ tại `ALLOW_COMPLETION.await(...)`, nên nó **không thể in `WORK_DONE` trước `PUBLISH_RETURNED`**.
4. Main in `PUBLISH_RETURNED`, mở latch cho worker và rời khỏi `try-with-resources`. Điều này gọi `context.close()`.
5. Executor được cấu hình drain work và await tối đa 10 giây. Với task ngắn của ví dụ, worker in `WORK_DONE` trước khi `context.close()` hoàn tất, nên `CONTEXT_CLOSED` nằm cuối.

Chú ý: chương trình dùng latch để **chứng minh việc có worker riêng và xác định thứ tự**. Nó không chứng minh rằng mọi task production đều hoàn tất khi timeout hết; nhiệm vụ có thể bị treo mạng, chạy nhiều giờ hoặc không tôn trọng interrupt. Trong ví dụ, `awaitTerminationSeconds(10)` và timeout latch được chọn đủ cho một công việc gần như tức thời, với giả định môi trường thực thi bình thường.

### 6.5. Vì sao không gọi executor.shutdown() trong main?

`ThreadPoolTaskExecutor` là bean có lifecycle do Spring quản lý. Việc gọi `shutdown()` thủ công khi context còn mở có thể khiến những listener khác bị từ chối, trong khi context vẫn nghĩ bean đang phục vụ các thành phần khác. Khi đóng context, Spring đã có đường destruction chính thức. Nếu muốn không nhận công việc mới, hãy điều phối **producer stop → consumer drain → resource destroy** bằng lifecycle policy thay vì tùy tiện shutdown một bean đang được chia sẻ.

### 6.6. Vì sao không gọi initialize() trong @Bean?

Khi trả `ThreadPoolTaskExecutor` như một Spring bean, container áp dụng `InitializingBean.afterPropertiesSet()` và các callback khởi tạo phù hợp. Gọi `initialize()` thủ công rồi để container khởi tạo lại là thừa và có thể gây hành vi không mong muốn. Ngược lại, nếu bạn tạo executor bằng `new` **ngoài** Spring, bạn phải chủ động khởi tạo/đóng theo đúng API.

## 7. Nếu Spring context đóng khi queue còn task?

Trong demo chỉ có một task. Trong ứng dụng thực, một executor có thể có task đang chạy và nhiều task nằm trong queue:

~~~text
                RUNNING: [A] [B]
                QUEUED : [C] [D] [E] [F]

Context.close()
    |
    +-- strict/early shutdown: giới hạn nhận task mới
    |
    +-- coordinated lifecycle stop hoặc destruction policy
    |
    +-- xử lý A/B/C/D/E/F hoặc ngắt/loại bớt theo config
    |
    +-- đợi tối đa awaitTerminationSeconds
    |
    +-- đóng các bean còn lại
~~~

Không thể chỉ nhìn `@Async` mà biết C/D/E/F có được chạy hay không. Cần biết loại executor, `waitForTasksToCompleteOnShutdown`, `strictEarlyShutdown`, timeout và chính sách rejection. Với `waitForTasksToCompleteOnShutdown(true)`, queue được dành cơ hội chạy trong shutdown; tuy nhiên việc **hoàn tất tác vụ** vẫn cần thời gian và sự hợp tác của task.

### 7.1. Phân biệt task đã được lên lịch và task đã thành công

Một `publishEvent` không ném lỗi và một `executor.execute(...)` được chấp nhận chỉ chứng minh việc **submit** thành công theo API; chưa chứng minh tác vụ đã thực thi hoặc side effect bền vững.

Với tác vụ quan trọng, theo dõi trạng thái:

~~~text
PENDING -> RUNNING -> SUCCEEDED
                  \-> RETRYABLE_FAILED -> PENDING
                  \-> PERMANENT_FAILED
~~~

Những trạng thái này thuộc job system hoặc storage do ứng dụng định nghĩa, không phải field có sẵn của mọi Spring TaskExecutor.

### 7.2. Bị từ chối trong lúc dừng

Nếu producer tiếp tục gửi event sau khi pool không nhận task, `@Async` có thể gặp `TaskRejectedException` hoặc `RejectedExecutionException` theo implementation. Đây là lỗi **submit**, khác với exception do thân listener ném sau khi đã nhận task.

Hãy xác định policy rõ: dừng producer trước, ghi metric rejected tasks, retry ở tầng thích hợp nếu công việc cần giao lại. Đừng tự coi lỗi submit là “email đã được gửi” hoặc im lặng nuốt lỗi khi thông điệp bắt buộc.

## 8. ContextClosedEvent, @PreDestroy và SmartLifecycle dùng khi nào?

Ba cơ chế này phục vụ các việc khác nhau.

### 8.1. ContextClosedEvent: quan sát giai đoạn đóng

`ContextClosedEvent` được phát trong quá trình `ApplicationContext` đóng. Listener có thể cập nhật một cờ trạng thái, ghi log và phối hợp quá trình dừng theo hợp đồng. Nhưng không nên dùng listener async của chính event này để mặc định gửi tác vụ “bắt buộc phải hoàn tất trước JVM thoát”, vì executor có thể đang dừng trong cùng giai đoạn.

### 8.2. @PreDestroy: dọn tài nguyên của bean

Nếu một bean **thật sự sở hữu** tài nguyên ngoài container, `@PreDestroy` hoặc `DisposableBean.destroy()` có thể đóng nó. Với executor đã là Spring-managed `ThreadPoolTaskExecutor`, **không cần thêm @PreDestroy chỉ để gọi shutdown cho cùng bean**, tránh quản lý trùng.

Nếu bean sở hữu kết nối/file/resource khác, cleanup là trách nhiệm của bean đó, không nên cố chuyển việc cleanup bắt buộc thành một sự kiện async.

### 8.3. SmartLifecycle: phối hợp start/stop theo phase

Một component nhận dữ liệu từ Kafka, WebSocket, polling hoặc scheduler có thể triển khai `SmartLifecycle` để:

- Bắt đầu nhận công việc khi context đã đạt điều kiện phù hợp.
- Dừng producer và ngừng tạo task mới khi shutdown.
- Theo dõi các việc đang xử lý, phối hợp callback `stop(Runnable)`.
- Chọn `getPhase()` để xác định thứ tự stop theo policy của Spring.

Thông thường, lifecycle processor xử lý **stop theo phase đảo** so với start: phase cao có thể được dừng trước phase thấp. Nhưng thứ tự cuối còn chịu ảnh hưởng dependency giữa bean và cấu hình lifecycle. Không suy luận chỉ từ phase nếu có quan hệ phụ thuộc rõ.

Pseudo-code thể hiện ý định:

~~~text
SmartLifecycle producer:
  start():  allowNewMessages = true
  stop(callback):
     allowNewMessages = false
     stopPollingNewMessages()
     waitUntilInFlightIsSafeOrTimedOut()
     callback.run()

Executor:
  drainAcceptedTasksAccordingToPolicy()
  shutdown()
~~~

Đây là pseudo-code, **không phải class Java biên dịch trực tiếp**. Khi triển khai `SmartLifecycle.stop(Runnable)` thực tế, luôn phải gọi callback khi quá trình dừng kết thúc để container không chờ mãi (và cần xử lý failure/timeout). Nếu stop không đồng bộ, phase timeout phải được cấu hình phù hợp.

### 8.4. Không có một “thứ tự chung” cho mọi bean

Ví dụ callback `@PreDestroy` của một bean có thể chạy khi một executor đã ngừng nhận task. Một thiết kế phụ thuộc “trong destroy tôi sẽ submit một job async rồi chờ nó” có rủi ro deadlock hoặc rejection. Đặc biệt không làm blocking wait bên trong cùng pool có số worker thấp nếu tác vụ được chờ cũng cần worker của pool đó.

## 9. ExecutorService của JDK khi cần quản lý thủ công

Đôi khi thư viện không dùng `ThreadPoolTaskExecutor` mà tạo trực tiếp `ExecutorService`. Nếu đó là bean Spring do bạn quản lý, có thể khai báo destruction callback:

~~~java
@Bean(destroyMethod = "shutdown")
ExecutorService reportingPool() {
    return Executors.newFixedThreadPool(2);
}
~~~

Đây là đoạn minh họa cần import `Bean`, `ExecutorService` và `Executors`, và nằm trong một class cấu hình. Khi context destroy bean, Spring gọi `shutdown()`. Nhưng `shutdown()` của JDK **chỉ yêu cầu ngừng nhận task mới và xử lý task đã submit**, không tự block đợi mọi task xong; nếu cần đợi, phải kết hợp `awaitTermination(...)` theo policy.

Với một executor tự sở hữu hoàn toàn, mẫu shutdown JDK:

~~~java
pool.shutdown();
try {
    if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
        pool.shutdownNow();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            System.err.println("Executor did not terminate");
        }
    }
} catch (InterruptedException ex) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

Đây là đoạn code minh họa **đặt trong lifecycle hook của owner**, cần biến `pool` kiểu `ExecutorService` và import `TimeUnit`/`InterruptedException`. `shutdownNow()` là yêu cầu ngắt/hủy best-effort; nó không bảo đảm mọi task sẽ lập tức kết thúc. Sau khi timeout, phải có quan sát và cơ chế phục hồi nếu công việc quan trọng.

**Không dùng đồng thời hai owner:** nếu Spring quản lý việc hủy `ThreadPoolTaskExecutor` rồi bạn lại tự gọi shutdown trong nhiều listener khác, sẽ khó dự đoán lúc pool bắt đầu từ chối task.

## 10. Thread context, transaction và task còn chạy lúc shutdown

Bởi task async chạy trên worker thread, nó thường **không kế thừa transaction imperative** đang gắn với publisher thread:

~~~text
Publisher thread                        events-1 worker
----------------------                  -----------------------
@Transactional T1
 save Order
 publish(OrderPlaced)  -----------+---> listener @Async
 COMMIT T1                          |     update projection
 return                             |     own transaction if configured
                                    +---> shutdown may begin meanwhile
~~~

Một listener `@Async` lỗi **không tự rollback transaction nguồn**. Listener cần thao tác DB nhất quán thì dùng service `@Transactional` trên worker qua Spring proxy, tạo transaction đúng phạm vi của nó.

Nếu chỉ muốn xử lý khi transaction nguồn đã commit, cân nhắc `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`, có thể kết hợp `@Async`. Nhưng:

- AFTER_COMMIT chỉ điều phối **thời điểm** theo transaction; không bảo đảm task chắc chắn được giao và hoàn tất.
- Nếu publish ngoài transaction, handler mặc định không chạy khi không bật `fallbackExecution=true`.
- Lỗi/timeout/shutdown của executor có thể xảy ra sau khi transaction đã commit.
- Nếu listener sau commit ghi DB, nên mở transaction mới phù hợp, không dựa vào transaction cũ.
- Một cơ chế shutdown chờ task trong RAM không đồng nghĩa **durable delivery**.

### Không bê nguyên ThreadLocal sang worker

MDC, security context, locale, request context hay tracing context có thể cần được truyền qua `TaskDecorator`/thư viện context propagation nếu hợp đồng cho phép. Nhưng **không tự copy JDBC/JPA transaction** hoặc EntityManager từ publisher sang worker. Việc cố dùng cùng session/entity ở thread khác rất dễ gặp lỗi và vi phạm ranh giới transaction.

Khi shutdown, những dependency như HTTP client, connection pool và logger cũng có lifecycle riêng. Cần bảo đảm thứ tự đóng phù hợp; chờ task của executor trong khi dependency của task đã bị destroy có thể vẫn thất bại.

## 11. Exception trong async task và exception khi shutdown

Cần phân biệt ít nhất bốn đường lỗi:

| Loại lỗi | Ví dụ | Nơi quan sát |
| --- | --- | --- |
| **Scheduling rejection** | Queue đầy, executor đang shutdown | Thread submit, error handling của đường executor |
| **Exception trong @Async void** | HTTP 503, serialization lỗi | `AsyncUncaughtExceptionHandler` nếu exception không được bắt |
| **Task bị interrupt** | Shutdown/cancel/timeout | Trong task qua `InterruptedException` hoặc interrupt flag |
| **Termination timeout** | Worker không dừng trong budget | Shutdown path, metrics/log vận hành |

Một `try/catch` quanh `publishEvent(...)` không đủ để bắt exception phát sinh bên trong worker đã chạy async. `SimpleApplicationEventMulticaster.setErrorHandler(...)` và `AsyncUncaughtExceptionHandler` cũng là **hai lớp xử lý khác nhau**, không nên cho rằng một handler bao hết mọi kiểu lỗi.

### 11.1. Interrupt phải được xử lý đúng

Một task nên:

- Tôn trọng `InterruptedException` ở điểm blocking phù hợp.
- Khôi phục interrupt flag khi chuyển exception sang loại khác: `Thread.currentThread().interrupt()`.
- Không tiếp tục vòng lặp vô hạn sau khi đã được yêu cầu dừng.
- Không giả định interrupt tự rollback email/API bên ngoài đã hoàn tất.

Ví dụ phương thức xử lý:

~~~java
try {
    blockingQueue.take();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Đây là mã minh họa trong một method có `blockingQueue` tương ứng. Việc im lặng nuốt interrupt có thể khiến container không dừng được task trong thời hạn graceful shutdown.

### 11.2. Không để lỗi bị nuốt trong error handler

Handler exception có thể ghi structured log, metric, trạng thái thất bại hoặc gửi job retry. Nhưng “đã log” không đồng nghĩa “đã xử lý xong”. Nếu task bắt buộc phải hoàn thành, phải có cơ chế lưu kết quả và xử lý lại bền vững.

## 12. Shutdown ở môi trường triển khai: thứ tự stop producer, drain, destroy

Khi chạy trong Kubernetes, VM, service manager hoặc application server, process thường có **một khoảng thời gian hữu hạn** để dừng. Vì vậy timeout executor phải phối hợp với thời gian của nền tảng và các thành phần khác.

Một kịch bản vận hành nên xác định:

1. **Ngừng nhận input mới:** bỏ readiness, dừng poll/consumer/scheduler theo thứ tự được thiết kế.
2. **Chốt trạng thái công việc:** những task đã nhận sẽ hoàn tất trong budget hoặc được ghi nhận cho retry.
3. **Drain executor:** đợi công việc đang chạy và trong queue theo policy.
4. **Đóng dependency:** connection pool, HTTP client, resource khác đóng sau khi những task cần chúng đã ngừng.
5. **Kết thúc process:** trước deadline do orchestrator/service manager áp đặt.

Không đặt `awaitTerminationSeconds(120)` nếu nền tảng sẽ kill container sau 30 giây rồi nghĩ đã có hai phút graceful shutdown. Ngược lại, timeout 1 giây cho hàng nghìn task trong queue có thể khiến rất nhiều task còn dang dở.

### Thiết kế budget

~~~text
Giả sử deadline của nền tảng: 45 giây
  - stop producer / readiness: tối đa 5 giây
  - drain accepted work    : tối đa 25 giây
  - close dependencies      : tối đa 10 giây
  - safety margin           : 5 giây
~~~

Các số chỉ là **ví dụ lập kế hoạch**, không phải benchmark. Trong triển khai thật, đo p95/p99 thời gian task, backlog, tốc độ tiêu thụ, timeout của downstream và khả năng interruption. Giám sát shutdown duration và số task chưa hoàn thành.

### Metrics gợi ý

Tên dưới đây là metric **ứng dụng tự định nghĩa**, không phải tất cả đều được Spring tạo sẵn:

~~~text
app_event_executor_active_threads
app_event_executor_queue_depth
app_event_executor_rejected_total
app_event_executor_shutdown_duration_seconds
app_event_executor_inflight_on_close
app_event_executor_unfinished_total
app_event_listener_failures_total{listener="notification"}
~~~

Đừng đặt `eventId`/`orderId` làm metric label để tránh cardinality cao; giữ những ID đó trong structured logs/traces.

## 13. Vì sao chờ đúng lifecycle vẫn không bảo đảm delivery?

Ngay cả khi một task được cho chạy đến khi `context.close()` trả về, hệ thống vẫn phải xử lý những tình huống:

- Process bị kill mà không gọi được Java shutdown hook.
- Node mất nguồn, kernel panic hoặc container bị kill cứng.
- Gửi email thành công nhưng trả timeout, retry có thể gửi trùng.
- Thread pool dừng sau khi transaction nguồn commit nhưng task chưa được lưu bền vững.
- Một consumer đã nhận event nhưng crash trước khi ghi trạng thái hoàn thành.

**TaskExecutor không phải message broker/event store.** Với công việc cần tin cậy, nên lưu ý định công việc **cùng transaction** với trạng thái nghiệp vụ qua **transactional outbox**, rồi dispatcher giao task với retry/idempotency.

~~~text
T1 BEGIN
  save order
  insert outbox(id, eventType, payload, status=PENDING)
T1 COMMIT
            |
            v
Outbox worker / broker
  -> deliver idempotently
  -> retry transient failure
  -> record success / dead-letter
~~~

Nếu T1 rollback, không có event outbox commit. Nếu T1 commit rồi process chết, bản ghi pending vẫn có thể được khôi phục và gửi lại. Hệ thống thường cung cấp **at-least-once delivery** với deduplication; không tự hứa exactly-once end-to-end.

Đây là giải pháp cho **độ tin cậy**, không thay thế hoàn toàn việc đóng thread pool đúng lifecycle. Cả hai vấn đề đều cần được xử lý nhưng thuộc hai tầng khác nhau.

## 14. Kiểm thử shutdown đúng cách

Một test chất lượng không chỉ assert `context.close()` không ném exception, mà cần biết task nào được nhận, chạy, hoàn tất hoặc bị từ chối.

| Tình huống | Kỳ vọng cần xác minh |
| --- | --- |
| Context có executor bean và không có task | Context close sạch, thread pool không rò rỉ |
| Một async listener đang chạy | Close tuân theo thời gian chờ/policy, không ngắt ngoài ý muốn |
| Có task trong queue | `waitForTasksToCompleteOnShutdown(true)` xử lý queue theo hợp đồng |
| Timeout ngắn hơn thời gian task | Quan sát task chưa hoàn tất và kế hoạch recovery, không coi tất cả thành công |
| Strict early shutdown | Sau tín hiệu close, submission mới bị từ chối theo policy |
| Producer vẫn submit khi shutdown | Không có vòng lặp tạo task vô hạn; có handling rejection |
| Executor phụ thuộc DataSource | Task cần DB không chạy sau khi DB đã bị destroy nếu yêu cầu an toàn |
| Async listener ném exception | Error handler/metric nhận lỗi và shutdown không báo thành công giả |
| Thread bị interrupt | Task phục hồi interrupt flag hoặc dừng hợp lệ |
| Nhiều service cùng dùng pool | Không service nào tự shutdown một shared bean khi context còn hoạt động |
| Container bị kill trước await timeout | Job bền vững có thể retry sau restart |
| Context cha–con hoặc nhiều ApplicationContext | Mỗi executor có owner/lifetime rõ, không dùng bean đã đóng |

### 14.1. Dùng latch thay Thread.sleep

Ví dụ mục 6 dùng `CountDownLatch` và timeout 10 giây để tạo quan hệ thứ tự xác định. Một test dựa vào `Thread.sleep(100)` rất dễ flaky vì scheduling và tải CI không cố định.

Với test timeout, nên chủ động giữ worker bằng latch, bắt đầu close ở thread kiểm thử riêng và quan sát thời điểm hoàn tất. Test này phải có cơ chế release task cuối cùng để không treo cả suite, kể cả khi assertion thất bại.

### 14.2. Theo dõi tiến trình

Ngoài assert dữ liệu, nên giám sát:

- Số task đã submit / đang chạy / đang queue.
- Số task thành công và thất bại.
- Số task bị reject khi close.
- Thời gian shutdown thực tế.
- Task còn dang dở khi budget hết.
- Số job được khôi phục từ outbox sau restart.

Có thể tạo test giả lập restart để kiểm tra **job delivery** tách biệt với test graceful close của executor.

## 15. Những lỗi phổ biến

1. **Tạo pool bằng new ở mỗi listener** mà không lưu tham chiếu để shutdown.
2. **Khai báo ThreadPoolTaskExecutor như bean nhưng tự gọi initialize() lần nữa** mà không cần thiết.
3. **Tự gọi shutdown() từ business method**, làm các listener khác bị reject trong khi context vẫn hoạt động.
4. **Cho rằng context.close() mặc nhiên drain toàn bộ queue** bất kể flag/timeout.
5. **Đặt waitForTasksToCompleteOnShutdown(true) rồi nghĩ pool từ chối task ngay khi ContextClosedEvent phát ra**; flag này dùng shutdown mềm muộn trong destruction phase.
6. **Bật strictEarlyShutdown(true) cùng waitForTasksToCompleteOnShutdown(true) rồi tưởng strict vẫn áp dụng nguyên vẹn**; phải đọc tương tác flag.
7. **Chỉ bật waitForTasksToCompleteOnShutdown nhưng không có awaitTerminationSeconds** trong khi task phụ thuộc các bean khác đang bị destroy.
8. **Coi awaitTerminationSeconds như bảo đảm task chắc chắn hoàn tất**; nó là maximum blocking budget.
9. **Để producer tiếp tục phát task trong shutdown** làm pool liên tục bị reject hoặc backlog không hội tụ.
10. **Gọi @Async cleanup từ @PreDestroy và chờ trên chính pool đã shutdown**, dễ bị rejection/deadlock.
11. **Bỏ qua InterruptedException** và tiếp tục loop nên JVM khó dừng.
12. **Bắt toàn bộ exception rồi nuốt** khiến task lỗi nhưng hệ thống báo thành công.
13. **Dùng queue không giới hạn cho tác vụ quan trọng**, che giấu overload và khiến drain mất kiểm soát.
14. **Không phối hợp timeout với deadline Kubernetes/service manager**, process bị kill trước khi drain.
15. **Tin rằng graceful shutdown là durable delivery**, trong khi kill cứng và crash không được giải quyết.
16. **Đưa cả email/payment thao tác ngoài vào một transaction tưởng tượng của async worker**, nhầm rollback và eventual consistency.
17. **Không đo task rejection lúc context đóng**, làm mất event âm thầm.
18. **Không tách trách nhiệm producer và executor**, thiếu người điều phối stop sequence.
19. **Dùng ContextClosedEvent để phát async task bắt buộc** dù executor có thể đã hoặc đang ngừng nhận.
20. **Không test timeout và shutdown khi có task bị treo**, chỉ test lúc không có tải.

## 16. Bài tập tự kiểm tra

1. Khi `ThreadPoolTaskExecutor` được khai báo `@Bean`, ai chịu trách nhiệm khởi tạo và destroy pool?
2. `waitForTasksToCompleteOnShutdown(true)` khác `awaitTerminationSeconds(30)` ở điểm nào?
3. Vì sao `setStrictEarlyShutdown(true)` có thể không còn chi phối khi `setWaitForTasksToCompleteOnShutdown(true)`?
4. Nếu Spring context đóng còn 10 task queued, có thể khẳng định cả 10 đều chạy thành công chỉ vì `context.close()` không lỗi không?
5. Trong demo, điều gì bảo đảm `WORK_DONE` không được in trước `PUBLISH_RETURNED`?
6. Nếu pool đã reject task mới lúc shutdown, lỗi đó thuộc submit hay thân worker?
7. Nếu `@Async` listener gửi email lỗi sau khi publisher commit order, nó có thể rollback order bằng exception không?
8. Vì sao không nên dùng `@PreDestroy` để phát một nhiệm vụ `@Async` bắt buộc trong cùng executor?
9. Khi một executor phụ thuộc DB và HTTP client, tại sao thời gian chờ phải phối hợp với thứ tự destroy dependencies?
10. Trong môi trường có 30 giây termination grace period, điều gì xảy ra nếu bạn cấu hình await termination 120 giây?
11. Vì sao `ExecutorService.shutdown()` khác `awaitTermination(...)`?
12. Đối với công việc không được mất sau crash, cần bổ sung cơ chế gì ngoài Spring event executor?
13. `SmartLifecycle.stop(Runnable)` nên thông báo hoàn tất bằng cách nào?
14. Một listener chạy trong thread pool có tự kế thừa `@Transactional` của publisher không?

**Gợi ý trả lời:** (1) Spring context; (2) policy xử lý task vs thời gian block chờ; (3) flag wait-for-completion làm shutdown muộn và override early signal; (4) không, phụ thuộc policy/thời gian/exception; (5) latch chặn worker cho đến sau log; (6) lỗi scheduling; (7) không, transaction nguồn đã commit; (8) pool có thể đã ngừng nhận và shutdown bị treo; (9) worker cần resource còn sống; (10) nền tảng có thể kill tiến trình sớm; (11) yêu cầu stop nhận mới vs chờ kết thúc; (12) outbox/job bền vững + retry/idempotency; (13) gọi callback khi stop hoàn tất; (14) không tự động với imperative thread-bound transaction.

## 17. Tổng kết

**Đóng executor đúng lifecycle** có nghĩa là có owner rõ ràng, hiểu cách Spring context phối hợp stop/destroy, chọn policy nhận task mới và drain work, chờ tối đa hợp lý, đảm bảo các dependency cần thiết còn sống, và có cách quan sát lỗi/unfinished work. Với Spring-managed `ThreadPoolTaskExecutor`, ưu tiên để container quản lý vòng đời thay vì shutdown thủ công từ listener.

Ba cấu hình thường bị nhầm là:

- `setWaitForTasksToCompleteOnShutdown(true)`: ưu tiên hoàn thành task đang chạy và queued khi shutdown, có trade-off về late submission/coordinated stop.
- `setAwaitTerminationSeconds(n)`: chờ tối đa n giây để executor kết thúc trước khi destroy tiếp, không tự bảo đảm hoàn tất.
- `setStrictEarlyShutdown(true)`: tín hiệu dừng nhận task sớm theo policy, nhưng có thể bị các flag khác override.

Cuối cùng, executor chỉ là **cơ chế thực thi trong bộ nhớ**. Graceful shutdown tốt không loại bỏ các trường hợp crash/kill cứng. Với công việc nghiệp vụ phải được giao và xử lý tin cậy, dùng cơ chế bền vững như **transactional outbox**, consumer idempotent và retry có giám sát.

## Tài liệu tham khảo

- Spring Framework 6.2.8 API — *ExecutorConfigurationSupport*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html
- Spring Framework 6.2.8 API — *ThreadPoolTaskExecutor*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.2 Reference — *Task Execution and Scheduling*: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework Reference — *Application Events and Async Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework 6.2.8 API — *AbstractApplicationContext*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework 6.2.8 API — *SmartLifecycle*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/SmartLifecycle.html
