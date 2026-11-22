# Executor mặc định và executor tùy biến trong Spring Async

## 1. Mục tiêu

Khi một method được đánh dấu @Async, Spring không tự tạo một thread tùy ý cho từng method. Spring gửi công việc tới một Executor được cấu hình trong ApplicationContext. Executor quyết định task chạy trên thread nào, có được xếp hàng hay không, mức độ đồng thời tối đa và cách xử lý khi hệ thống quá tải.

Nếu ứng dụng chỉ có một nhóm công việc nhỏ, một executor mặc định có thể đủ. Khi hệ thống có nhiều loại công việc, chẳng hạn gửi email, xử lý ảnh, gọi dịch vụ bên ngoài hoặc tính toán CPU, các nhóm công việc có thể cần pool riêng để tránh chiếm dụng tài nguyên của nhau.

Bài học tập trung vào:
- TaskExecutor và Executor khác nhau ở đâu.
- Spring Framework chọn executor mặc định cho @Async theo thứ tự nào.
- Khi nào SimpleAsyncTaskExecutor được dùng và vì sao nó không phải thread pool.
- Cách khai báo ThreadPoolTaskExecutor có giới hạn và đặt tên thread.
- Cách chỉ định executor riêng bằng @Async("beanName").
- Cách dùng AsyncConfigurer để tùy biến executor mặc định và xử lý exception.
- Cách chọn queue, pool size, rejection policy và shutdown behavior.
- Sự khác nhau giữa default executor của Spring Framework và auto-configuration của Spring Boot.

Sau bài học, bạn có thể dự đoán một method @Async sẽ chạy trên executor nào, tách workload thành các pool phù hợp và phát hiện những cấu hình dễ gây queue tăng vô hạn hoặc làm caller phải chạy task đồng bộ.

## 2. Executor và TaskExecutor

Trong Java, java.util.concurrent.Executor là một abstraction nhận Runnable và quyết định cách thực thi task. Executor có thể dùng thread pool, một thread đơn, hoặc thậm chí thực thi ngay trên thread gọi. Tên Executor không bảo đảm implementation luôn là một pool.

Spring cung cấp org.springframework.core.task.TaskExecutor với hợp đồng execute(Runnable). TaskExecutor tương thích với java.util.concurrent.Executor và giúp các thành phần Spring dùng chung abstraction thực thi task.

Một số implementation thường gặp:

| Implementation | Hành vi | Khi phù hợp |
|---|---|---|
| SyncTaskExecutor | Chạy task ngay trên thread gọi | Test đơn giản hoặc cần thực thi đồng bộ |
| SimpleAsyncTaskExecutor | Tạo thread mới cho mỗi task, không tái sử dụng thread | Workload nhỏ hoặc trường hợp có concurrency limit rõ ràng |
| ThreadPoolTaskExecutor | Quản lý ThreadPoolExecutor có pool và queue | Lựa chọn phổ biến cho xử lý nền trong ứng dụng |
| ConcurrentTaskExecutor | Adapter cho một java.util.concurrent.Executor có sẵn | Khi cần tích hợp executor khác với abstraction Spring |

Với @Async, executor được dùng để thực thi method sau khi async interceptor nhận lời gọi qua proxy. Cấu hình executor ảnh hưởng trực tiếp tới khả năng chịu tải và độ trễ của hệ thống.

## 3. Spring chọn executor mặc định như thế nào?

Trong Spring Framework 6.2, nếu không có AsyncConfigurer cung cấp executor mặc định, Spring tìm executor theo quy tắc:

1. Tìm một bean TaskExecutor duy nhất trong ApplicationContext.
2. Nếu không phân giải được một TaskExecutor duy nhất, tìm bean có tên taskExecutor và kiểu tương thích với Executor.
3. Nếu không tìm thấy executor phù hợp, Spring dùng SimpleAsyncTaskExecutor làm fallback.

Nếu cấu hình triển khai AsyncConfigurer, phương thức getAsyncExecutor() cung cấp executor mặc định cho các method @Async không chỉ định qualifier. Nếu chỉ tùy biến exception handler hoặc muốn giữ executor mặc định, có thể để getAsyncExecutor() trả về null.

Có thể hình dung:

~~~text
@Async method không có qualifier
          |
          v
Có AsyncConfigurer trả về Executor?
       /             \
     Có               Không
     |                  |
     v                  v
Dùng Executor       Có đúng một TaskExecutor?
của configurer       /             \
                   Có               Không
                   |                  |
                   v                  v
             Dùng bean đó      Có bean tên taskExecutor?
                                  /          \
                                Có            Không
                                |               |
                                v               v
                         Dùng taskExecutor  SimpleAsyncTaskExecutor
~~~

Một method có qualifier sẽ chọn executor theo qualifier đó, không phụ thuộc vào executor mặc định:

~~~java
@Async("mailExecutor")
public void sendMail(String address) {
    // Chạy bằng executor có bean name hoặc qualifier mailExecutor.
}
~~~

Giá trị trong @Async có thể là tên một Executor bean hoặc qualifier gắn với một Executor bean, ví dụ thông qua @Qualifier.

Không nên giả định một bean bất kỳ tên applicationTaskExecutor sẽ tự động là executor mặc định của Spring Framework thuần. Tên mặc định mà Spring Framework tìm ở bước fallback là taskExecutor. applicationTaskExecutor thường xuất hiện trong các quy ước tích hợp và auto-configuration của Spring Boot.

## 4. SimpleAsyncTaskExecutor không phải thread pool

Nếu Spring Framework không tìm thấy executor phù hợp, fallback SimpleAsyncTaskExecutor có thể tạo một thread mới cho mỗi lần thực thi. Nó không tái sử dụng các thread đã hoàn tất như ThreadPoolTaskExecutor.

SimpleAsyncTaskExecutor có thể giới hạn số task đồng thời. Khi đạt giới hạn, các lần submit tiếp theo có thể phải chờ cho tới khi có slot trống. Tuy nhiên, concurrency limit không biến nó thành một pool tái sử dụng thread.

Điều này quan trọng khi workload tăng:
- Số lần gọi @Async lớn có thể dẫn tới nhiều thread được tạo.
- Thread mới tiêu tốn stack memory và tài nguyên hệ điều hành.
- Không có queue/pool reuse như ThreadPoolTaskExecutor.
- Việc giới hạn đồng thời vẫn cần được cấu hình và quan sát rõ.

Vì vậy, với workload production cần kiểm soát số thread, queue và rejection, hãy khai báo executor tường minh. Đừng coi fallback là một thread pool đã được sizing cho ứng dụng.

## 5. Khai báo ThreadPoolTaskExecutor mặc định

ThreadPoolTaskExecutor là implementation phổ biến của Spring TaskExecutor. Nó bọc một ThreadPoolExecutor và cho phép cấu hình bằng các thuộc tính bean.

Ví dụ:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean(name = "taskExecutor")
    public ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("app-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
~~~

Vì executor được khai báo là Spring bean, Spring quản lý lifecycle của nó và gọi các bước initialize/shutdown cần thiết. Không cần gọi initialize() thủ công trong phương thức @Bean thông thường.

Các thuộc tính chính:

| Thuộc tính | Ý nghĩa |
|---|---|
| corePoolSize | Số worker thread cốt lõi của pool |
| maxPoolSize | Số worker thread tối đa khi queue đã đầy |
| queueCapacity | Số task có thể chờ trong queue |
| keepAliveSeconds | Thời gian thread vượt core có thể nhàn rỗi trước khi bị thu hồi |
| threadNamePrefix | Prefix giúp nhận diện executor trong log và thread dump |
| waitForTasksToCompleteOnShutdown | Yêu cầu executor chờ task đã nhận khi context shutdown |
| awaitTerminationSeconds | Thời gian chờ tối đa để executor kết thúc khi shutdown |

Đặt tên thread riêng cho từng pool giúp xác định task đang chạy ở executor nào. Ví dụ app-async-1 là thread của pool mặc định trong cấu hình trên.

## 6. Queue và pool size phối hợp ra sao?

ThreadPoolTaskExecutor dựa trên quy tắc của ThreadPoolExecutor. Khi một task mới được submit, executor xử lý theo thứ tự:

1. Nếu số worker đang chạy nhỏ hơn corePoolSize, tạo worker mới để chạy task.
2. Nếu đã đạt corePoolSize, thử đưa task vào queue nếu queue còn chỗ.
3. Nếu queue đã đầy, tạo thêm worker cho tới maxPoolSize.
4. Nếu queue đầy và pool đã đạt maxPoolSize, task bị từ chối theo rejection policy.

Ví dụ corePoolSize=2, maxPoolSize=4, queueCapacity=50:

- Hai task đầu có thể chạy trên hai worker cốt lõi.
- Khi hai worker bận, các task tiếp theo được xếp vào queue.
- Chỉ khi queue đầy, executor mới tăng số worker vượt core lên worker thứ ba hoặc thứ tư.
- Khi cả queue và pool đều đầy, task mới bị từ chối.

Đây là lý do queue capacity ảnh hưởng trực tiếp đến việc pool có mở rộng tới maxPoolSize hay không. Queue không giới hạn thường khiến executor tiếp tục xếp task vào queue và không cần tạo thêm worker vượt core. Trong trường hợp đó, maxPoolSize gần như không có tác dụng.

Không có một bộ thông số phù hợp cho mọi ứng dụng. Hãy đo thời gian xử lý, tốc độ submit, mức đồng thời và tài nguyên mà task sử dụng để chọn core, max và queue capacity.

## 7. Queue không giới hạn và nguy cơ quá tải

Queue capacity không giới hạn có vẻ giúp ứng dụng không từ chối task, nhưng nó có thể tích tụ công việc nhanh hơn tốc độ xử lý.

Khi producer gửi task liên tục mà worker không xử lý kịp:
- Queue tăng dần.
- Thời gian chờ trước khi task bắt đầu tăng.
- Các task giữ dữ liệu và object tham chiếu trong bộ nhớ lâu hơn.
- Ứng dụng có thể hết heap và gặp OutOfMemoryError.
- maxPoolSize có thể không được sử dụng vì executor ưu tiên queue trước.

Một queue hữu hạn tạo điểm kiểm soát tải. Khi queue đầy, executor phải tăng worker hoặc áp dụng rejection policy. Đây là tín hiệu để ứng dụng xử lý backpressure, giới hạn tốc độ submit hoặc đưa công việc sang một hệ thống queue bền vững.

Không chọn queue quá lớn chỉ để tránh TaskRejectedException. Queue lớn có thể che giấu tình trạng xử lý chậm và làm thời gian chờ tăng mà không cải thiện throughput.

## 8. Rejection policy khi executor quá tải

Khi queue đầy và pool đạt maxPoolSize, ThreadPoolExecutor cần một chính sách cho task mới. Spring ThreadPoolTaskExecutor mặc định sử dụng AbortPolicy; task bị từ chối và Spring biểu diễn lỗi dưới dạng TaskRejectedException.

Một số lựa chọn:

| Policy | Hành vi | Lưu ý |
|---|---|---|
| AbortPolicy | Ném lỗi khi không nhận task | Phù hợp khi caller cần biết task chưa được nhận |
| CallerRunsPolicy | Thread gọi submit tự chạy task | Tạo backpressure nhưng lời gọi có thể chạy đồng bộ |
| DiscardPolicy | Bỏ task mới | Chỉ dùng khi task có thể mất theo thiết kế |
| DiscardOldestPolicy | Bỏ task cũ nhất đang chờ rồi thử submit task mới | Có thể làm mất công việc đã được xếp hàng |

Ví dụ cấu hình CallerRunsPolicy:

~~~java
executor.setRejectedExecutionHandler(
    new ThreadPoolExecutor.CallerRunsPolicy()
);
~~~

CallerRunsPolicy có thể giảm tốc độ producer vì thread submit phải tự thực hiện task. Tuy nhiên, nó cũng làm thay đổi kỳ vọng của @Async: trong tình huống quá tải, caller có thể phải chạy công việc ngay trên thread của mình.

Với task nghiệp vụ quan trọng, không nên âm thầm discard. Hãy xác định rõ task nào có thể bỏ, task nào phải báo lỗi, task nào cần retry và task nào cần được lưu bền vững trong message broker hoặc database outbox.

## 9. Tạo nhiều executor và chọn theo từng method

Một ứng dụng có thể khai báo nhiều executor bean. Ví dụ, pool mặc định xử lý công việc nền chung, còn mailExecutor dành riêng cho gửi email.

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean(name = "taskExecutor")
    public ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("general-async-");
        return executor;
    }

    @Bean(name = "mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-async-");
        return executor;
    }
}
~~~

Dùng executor mặc định:

~~~java
@Async
public CompletableFuture<String> rebuildSearchIndex() {
    return CompletableFuture.completedFuture("index rebuilt");
}
~~~

Dùng executor riêng:

~~~java
@Async("mailExecutor")
public CompletableFuture<String> sendReceipt(String orderId) {
    return CompletableFuture.completedFuture("receipt sent: " + orderId);
}
~~~

Nếu không có AsyncConfigurer, Spring có thể thấy nhiều TaskExecutor bean nên không chọn được một bean duy nhất. Bean tên taskExecutor là lựa chọn fallback theo quy ước của Spring Framework. Method sendReceipt chỉ định mailExecutor nên được gửi vào pool đó.

Việc chia pool giúp workload độc lập hơn. Ví dụ, khi email service chậm, queue của mailExecutor tăng nhưng pool xử lý index vẫn có tài nguyên riêng. Tuy nhiên, các pool vẫn dùng chung CPU, heap, database connection và network; tạo nhiều pool không làm tổng tài nguyên của máy tăng lên.

## 10. Chọn executor theo loại workload

Cách chia executor nên phản ánh tài nguyên mà công việc sử dụng.

**I/O-bound:** gọi HTTP, gửi email, đọc file hoặc chờ phản hồi database thường dành nhiều thời gian chờ. Có thể cần nhiều task đồng thời hơn số CPU core, nhưng vẫn phải giới hạn theo connection pool và giới hạn của dịch vụ bên ngoài.

**CPU-bound:** nén ảnh, mã hóa hoặc tính toán nặng thường tiêu thụ CPU liên tục. Tăng thread quá mức có thể làm context switching và tranh chấp CPU tăng. Pool thường được sizing gần với năng lực CPU và đặc tính workload.

**Tác vụ ưu tiên thấp:** báo cáo, đồng bộ nền hoặc tái lập index có thể dùng pool riêng để không chiếm chỗ của luồng xử lý yêu cầu quan trọng.

Khi thiết kế nhiều pool, hãy trả lời:
- Task nào có thể chạy đồng thời?
- Task nào phải giữ thứ tự?
- Bao nhiêu task có thể chờ?
- Hệ thống phụ thuộc có giới hạn concurrency hoặc rate limit nào?
- Khi quá tải, task có thể bị từ chối, chạy trên caller hay phải được lưu lại?
- Khi ứng dụng shutdown, task đang chạy cần hoàn tất trong bao lâu?

Không chia pool chỉ theo tên module nếu các module vẫn tranh chấp cùng một tài nguyên giới hạn. Hãy phân chia theo mục tiêu cô lập và đặc tính thực thi.

## 11. AsyncConfigurer để tùy biến executor mặc định

Nếu muốn cung cấp executor mặc định bằng code thay vì dựa vào việc tìm bean, cấu hình có thể triển khai AsyncConfigurer.

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration implements AsyncConfigurer {

    @Bean
    @Override
    public Executor getAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(3);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(80);
        executor.setThreadNamePrefix("configured-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (exception, method, params) -> {
            System.err.println(
                "Async method failed: " + method.getName()
                + ", error=" + exception.getMessage()
            );
        };
    }
}
~~~

Trong ví dụ này, phương thức getAsyncExecutor() được khai báo là @Bean. Vì vậy, ThreadPoolTaskExecutor được Spring quản lý lifecycle và tự initialize/shutdown; không cần gọi initialize() thủ công.

AsyncConfigurer còn cho phép cung cấp AsyncUncaughtExceptionHandler cho method @Async trả về void. Nếu method trả về Future hoặc CompletableFuture, caller có thể quan sát lỗi thông qua future. Với void, exception không thể được truyền ngược trực tiếp về caller và mặc định Spring chỉ ghi log nếu không có handler riêng.

Các lớp cấu hình AsyncConfigurer được khởi tạo sớm trong quá trình bootstrap ApplicationContext. Nếu cần inject bean khác vào cấu hình này, hãy tránh kéo theo dependency khởi tạo sớm không cần thiết; ưu tiên cấu hình đơn giản và cân nhắc lazy dependency khi phù hợp.

Nếu chỉ cần một executor mặc định, có thể dùng bean taskExecutor thay vì AsyncConfigurer. AsyncConfigurer hữu ích khi muốn kiểm soát đồng thời default executor và uncaught exception handler.

## 12. TaskDecorator và context của thread

Executor thread không phải thread của request gọi @Async. Các dữ liệu gắn với ThreadLocal như MDC logging context không tự động được sao chép sang worker thread.

TaskDecorator cho phép bọc Runnable trước khi executor chạy task. Một decorator có thể:
1. Lấy context cần truyền từ thread submit.
2. Đặt context tương ứng trong thread thực thi.
3. Chạy task.
4. Khôi phục hoặc xóa context trong finally để tránh rò rỉ dữ liệu sang task tiếp theo dùng lại thread.

Ví dụ cấu hình:

~~~java
executor.setTaskDecorator(task -> {
    Map<String, String> context = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (context == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(context);
            }
            task.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    };
});
~~~

Ví dụ này minh họa việc truyền MDC; cần có dependency logging hỗ trợ MDC tương ứng. Với security context, request context hoặc transaction context, hãy dùng cơ chế tích hợp được hỗ trợ cho loại context đó. Không sao chép mọi ThreadLocal một cách tùy tiện vì có thể truyền nhầm dữ liệu nhạy cảm hoặc giữ reference không còn hợp lệ.

TaskDecorator hữu ích cho tracing và logging. Nó không biến executor thread thành thread của caller và không tự làm transaction imperative của caller tham gia vào task async.

## 13. Shutdown và vòng đời executor

ThreadPoolTaskExecutor là Spring-managed bean nên có lifecycle shutdown khi ApplicationContext đóng. Nếu ứng dụng cần chờ task đang chạy hoàn tất, có thể cấu hình:

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(30);
~~~

Cần phân biệt:
- Task đã được nhận có thể được tiếp tục xử lý trong giai đoạn shutdown tùy cấu hình.
- Thời gian chờ có giới hạn; task chạy quá lâu vẫn có thể không hoàn tất trước khi process kết thúc.
- Task mới có thể bị từ chối khi executor đã shutdown.
- Không có bảo đảm task đã nhận sẽ được phục hồi nếu process bị kill đột ngột.

Nếu task cần đảm bảo không mất, retry sau restart hoặc phân phối qua nhiều instance, một executor trong bộ nhớ không phải hàng đợi bền vững. Hãy cân nhắc message broker, persistent job store hoặc transactional outbox.

## 14. Spring Framework và Spring Boot có default khác nhau

Đây là khác biệt dễ gây nhầm lẫn.

Trong Spring Framework thuần, nếu không có AsyncConfigurer, không tìm được một TaskExecutor duy nhất và không có Executor bean tên taskExecutor, fallback là SimpleAsyncTaskExecutor. Implementation này không tái sử dụng thread như một thread pool.

Spring Boot có auto-configuration riêng cho task execution. Khi không có Executor bean tùy biến, Boot có thể cung cấp AsyncTaskExecutor mặc định; cấu hình thông thường dùng ThreadPoolTaskExecutor, còn cấu hình virtual threads có thể dùng SimpleAsyncTaskExecutor với Java 21+. Các quy tắc và bean được dùng còn phụ thuộc phiên bản Boot và cấu hình ứng dụng.

Vì vậy:
- Ví dụ trong bài dùng Spring Framework 6.2.0 thuần và tự khai báo taskExecutor.
- Không suy ra default của Spring Boot từ default của Spring Framework.
- Nếu dùng Boot, hãy đọc đúng tài liệu của phiên bản Boot và kiểm tra AsyncConfigurer, taskExecutor, applicationTaskExecutor cùng các auto-configuration đang hoạt động.
- Nếu nhiều integration như MVC, WebFlux, GraphQL và @Async cùng dùng executor, hãy kiểm tra tên bean và qualifier theo quy ước của Boot.

## 15. Ví dụ chạy được với Java 17+ và Spring Framework 6.2.0

Ví dụ này tạo hai executor:
- taskExecutor là executor mặc định cho method @Async không có qualifier.
- mailExecutor chỉ xử lý method được đánh dấu @Async("mailExecutor").

Chương trình gọi hai method qua bean proxy được ApplicationContext cung cấp. Kết quả trả về chứa thread name để quan sát executor thực tế.

### 15.1. Cấu trúc dự án

~~~text
spring-async-executors/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── async/
                        └── AsyncExecutorDemo.java
~~~

### 15.2. Cấu hình Maven

Tệp pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-async-executors</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 15.3. Chương trình minh họa

Tệp src/main/java/com/example/async/AsyncExecutorDemo.java:

~~~java
package com.example.async;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncExecutorDemo {

    public static class AsyncJobService {

        @Async
        public CompletableFuture<String> runDefault(String jobName) {
            String result = "default " + jobName
                    + " on " + Thread.currentThread().getName();

            return CompletableFuture.completedFuture(result);
        }

        @Async("mailExecutor")
        public CompletableFuture<String> sendMail(String recipient) {
            String result = "mail " + recipient
                    + " on " + Thread.currentThread().getName();

            return CompletableFuture.completedFuture(result);
        }
    }

    @Bean(name = "taskExecutor")
    public ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("default-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean(name = "mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(30);
        executor.setThreadNamePrefix("mail-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean
    public AsyncJobService asyncJobService() {
        return new AsyncJobService();
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             AsyncExecutorDemo.class)) {

            AsyncJobService service =
                    context.getBean(AsyncJobService.class);

            System.out.println(
                    "caller thread=" + Thread.currentThread().getName());

            String defaultResult =
                    service.runDefault("rebuild-index").join();

            System.out.println("default result=" + defaultResult);

            String mailResult =
                    service.sendMail("customer@example.test").join();

            System.out.println("mail result=" + mailResult);
        }
    }
}
~~~

Hai bean ThreadPoolTaskExecutor được Spring quản lý lifecycle. Do context có nhiều TaskExecutor, Spring không thể chọn một bean TaskExecutor duy nhất; bean tên taskExecutor là executor mặc định theo quy tắc Spring Framework. Method sendMail chỉ định mailExecutor nên dùng pool riêng.

Hai method trả về CompletableFuture. Việc gọi join() trong main chỉ để chương trình chờ kết quả và in stdout theo thứ tự dễ quan sát; trong ứng dụng thực tế, hãy kết hợp future theo luồng xử lý phù hợp thay vì block caller ngay sau khi submit.

### 15.4. Chạy chương trình

Từ thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=com.example.async.AsyncExecutorDemo
~~~

Stdout dự kiến:

~~~text
caller thread=main
default result=default rebuild-index on default-async-1
mail result=mail customer@example.test on mail-async-1
~~~

Kết quả cho thấy:
- Method runDefault dùng executor mặc định taskExecutor.
- Method sendMail dùng executor mailExecutor nhờ qualifier.
- Hai executor có thread name prefix riêng.
- Caller nhận CompletableFuture và lấy kết quả sau khi task hoàn tất.

Ví dụ chỉ có một task trên mỗi pool nên thread suffix là 1. Trong workload thật, nhiều task có thể chạy trên các worker khác nhau và thứ tự hoàn tất không được bảo đảm.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy executor mong muốn | Có nhiều TaskExecutor và không có bean taskExecutor phù hợp | Khai báo executor mặc định rõ ràng hoặc AsyncConfigurer |
| Method luôn chạy bằng executor mặc định | @Async thiếu qualifier hoặc qualifier sai | Dùng đúng @Async("beanName") |
| Nghĩ applicationTaskExecutor luôn là default | Nhầm quy ước Spring Boot với Spring Framework | Kiểm tra đúng framework và Boot version |
| Fallback tạo nhiều thread | Spring dùng SimpleAsyncTaskExecutor | Khai báo ThreadPoolTaskExecutor có giới hạn |
| maxPoolSize tăng nhưng pool không scale | Queue không giới hạn hoặc quá lớn | Dùng queue hữu hạn và đo tải |
| Queue tăng liên tục | Producer nhanh hơn consumer | Giới hạn submit, tăng throughput có kiểm soát hoặc dùng broker |
| Task bị từ chối | Queue và maxPoolSize đều đầy | Chọn rejection policy và xử lý TaskRejectedException |
| Caller bất ngờ chạy task | Dùng CallerRunsPolicy | Hiểu backpressure và ảnh hưởng tới latency của caller |
| Mất task khi ứng dụng tắt đột ngột | Executor chỉ lưu task trong bộ nhớ | Dùng message broker hoặc persistent job mechanism |
| Thread context bị mất | ThreadLocal không tự truyền qua executor | Dùng TaskDecorator hoặc integration phù hợp |
| Executor không shutdown đúng | Lifecycle bean hoặc wait policy chưa phù hợp | Để Spring quản lý bean và cấu hình shutdown rõ ràng |
| Async exception không được quan sát | Method void không có Future | Dùng AsyncUncaughtExceptionHandler và logging/metrics |

## 17. Checklist triển khai

- [ ] Xác định executor mặc định theo đúng Spring Framework hay Spring Boot.
- [ ] Có AsyncConfigurer thì hiểu getAsyncExecutor() đang chọn default nào.
- [ ] Nếu không dùng AsyncConfigurer, có unique TaskExecutor hoặc bean taskExecutor rõ ràng.
- [ ] Mỗi @Async qualifier trỏ tới đúng Executor bean.
- [ ] ThreadPoolTaskExecutor có core, max và queue capacity phù hợp.
- [ ] Queue có giới hạn khi workload cần kiểm soát memory.
- [ ] Rejection policy phù hợp với mức độ quan trọng của task.
- [ ] Thread name prefix khác nhau giữa các pool.
- [ ] Exception được quan sát qua Future hoặc AsyncUncaughtExceptionHandler.
- [ ] ThreadLocal context được truyền và dọn dẹp có chủ đích.
- [ ] Shutdown policy phù hợp với thời gian hoàn tất task.
- [ ] Công việc cần độ bền được lưu trong broker hoặc persistent store, không chỉ nằm trong executor memory.

## 18. Ghi nhớ

Trong Spring Framework 6.2, @Async dùng executor được cấu hình khi bật async processing. Nếu có AsyncConfigurer, getAsyncExecutor() cung cấp default. Nếu không, Spring tìm một TaskExecutor duy nhất, sau đó tìm Executor bean tên taskExecutor; nếu vẫn không có, fallback là SimpleAsyncTaskExecutor. Một method có thể chọn executor khác bằng @Async("beanName").

ThreadPoolTaskExecutor phù hợp khi cần giới hạn worker và queue. Executor ưu tiên core thread, sau đó queue, rồi mới tăng worker vượt core đến max; nếu queue và pool đều đầy, task bị từ chối. Queue không giới hạn có thể làm memory tăng và khiến maxPoolSize không phát huy tác dụng.

Hãy chia pool theo đặc tính workload, cấu hình rejection và shutdown rõ ràng, quan sát exception và thread context. Spring Boot có auto-configuration executor riêng, vì vậy luôn kiểm tra đúng phiên bản và quy ước bean đang được sử dụng.

## 19. Tài liệu tham khảo

- Spring Framework 6.2 — EnableAsync Javadoc:
  https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html
- Spring Framework 6.2 — AsyncConfigurer Javadoc:
  https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html
- Spring Framework 6.2 — Task Execution and Scheduling:
  https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 — ThreadPoolTaskExecutor Javadoc:
  https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Boot — Task Execution and Scheduling:
  https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html
