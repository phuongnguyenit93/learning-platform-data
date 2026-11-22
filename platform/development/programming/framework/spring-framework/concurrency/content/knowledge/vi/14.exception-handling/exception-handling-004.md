# Cấu hình bộ xử lý ngoại lệ bằng AsyncConfigurer

## 1. Vấn đề: @Async void lỗi nhưng caller không có Future để kiểm tra

Trong Spring Framework, `@Async` cho phép thực thi một phương thức bằng executor do Spring chọn. Khi method trả `void`, caller không có giá trị hay handle hoàn tất để nhận exception của task chạy sau đó trên worker. Ví dụ:

```java
import org.springframework.scheduling.annotation.Async;

@Async("backgroundExecutor")
public void notifyUser(String eventId) {
    throw new IllegalStateException("Không gửi được thông báo");
}
```

Đây là **mảnh method trong một Spring-managed bean**, không phải chương trình độc lập. Nếu lời gọi thực sự đi qua Spring async proxy và executor chạy task trên worker, exception phát sinh sau khi caller đã rời khỏi lời gọi. `try/catch` quanh `notifyUser(...)` ở caller thường không bắt được lỗi này.

Spring cung cấp `AsyncUncaughtExceptionHandler` để nhận lỗi **không thể truyền lại qua kiểu trả về** từ phương thức `@Async` trả `void`. Để thay handler mặc định trong Java Configuration, một lớp `@Configuration` triển khai `AsyncConfigurer` và override:

```java
@Override
public AsyncUncaughtExceptionHandler
        getAsyncUncaughtExceptionHandler() {
    return (exception, method, params) -> {
        // Ghi nhận exception từ @Async void.
    };
}
```

Điểm cần nhớ: **handler không phải công cụ bắt mọi exception của mọi task**. Method `@Async` trả `Future<T>` hoặc `CompletableFuture<T>` có kênh truyền lỗi qua kết quả; lỗi gửi việc (như executor bị từ chối) cũng khác lỗi trong thân task.

Bài học tập trung vào cách khai báo `AsyncConfigurer`, hợp đồng của `AsyncUncaughtExceptionHandler`, ví dụ Spring chạy được, phân biệt hai kênh báo lỗi, các rủi ro khi khởi tạo và thiết kế xử lý lỗi thực tế.

## 2. AsyncConfigurer nằm ở đâu trong luồng @Async?

Lỗi khi gửi tác vụ và lỗi xảy ra sau khi worker bắt đầu đã được phân biệt ở bài mở đầu của chương. Khi cấu hình Spring, điều quan trọng hơn là biết **lỗi nào do AsyncConfigurer phụ trách**.

| Ranh giới | Trách nhiệm cấu hình hoặc quan sát |
| --- | --- |
| Proxy lựa chọn executor và gửi công việc | Bean lookup lỗi, pool shutdown hoặc rejection có thể đi tới caller ngay; handler cho `@Async void` không bảo đảm nhận rejection. |
| Phương thức `@Async void` được worker chạy rồi ném exception chưa bắt | Async interceptor chuyển exception tới `AsyncUncaughtExceptionHandler` mà `AsyncConfigurer` cung cấp. |
| Phương thức `@Async Future` hoặc `CompletableFuture` thất bại | Caller quan sát exceptional completion của Future; handler dành cho void không phải nơi nhận kết quả. |

Vì thế cần **gọi bean qua Spring proxy** trong test và chọn executor có tên rõ ràng. Cấu hình đúng handler không thay thế cơ chế xử lý từ chối lúc submit, và không bảo đảm job đã được lưu bền vững.

## 3. AsyncConfigurer là điểm cấu hình nào?

Interface `org.springframework.scheduling.annotation.AsyncConfigurer` cho phép cấu hình hai thành phần tách biệt:

| Phương thức | Tác dụng | Có bắt buộc override cả hai không? |
|---|---|---|
| `getAsyncExecutor()` | Chọn `Executor` mặc định cho method `@Async` không chỉ rõ executor | Không |
| `getAsyncUncaughtExceptionHandler()` | Chọn handler cho lỗi không chuyển về caller từ `@Async void` | Không |

Từ các phiên bản Spring 6.x, các phương thức trên là default methods. Muốn thay handler, có thể chỉ override `getAsyncUncaughtExceptionHandler()`, để việc chọn executor theo bean name, qualifier hoặc quy tắc mặc định được cấu hình riêng.

Hợp đồng API rút gọn:

```java
public interface AsyncConfigurer {
    Executor getAsyncExecutor();
    AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler();
}
```

Đây là **sơ đồ chữ ký rút gọn**, không phải nguồn code đầy đủ: API thật có default implementations và annotation về nullable tùy phiên bản. Trong cấu hình thật cần import interface từ Spring và khai báo `@EnableAsync`.

**Không cần kế thừa `AsyncConfigurerSupport` ở ứng dụng Spring mới.** Class hỗ trợ này đã deprecated từ Spring Framework 6.0; triển khai trực tiếp `AsyncConfigurer` rõ ràng hơn.

Theo JavaDoc Spring, `AsyncConfigurer` thường được triển khai bởi class `@Configuration @EnableAsync`. Nó có thể **khởi tạo sớm trong ApplicationContext bootstrap**, nên cẩn thận khi inject những bean có proxy, transaction hoặc phụ thuộc phức tạp.

## 4. Dữ liệu lỗi mà AsyncConfigurer nên chuyển cho handler

`AsyncUncaughtExceptionHandler` có chữ ký `handleUncaughtException(Throwable error, Method method, Object... params)`. Bài trước đã giải thích hợp đồng và thời điểm handler chạy; ở đây trọng tâm là **thiết kế handler an toàn khi đăng ký vào Spring**.

- Dùng tên method/class và nhóm exception để ghi metric có cardinality hữu hạn; truyền cả Throwable vào logger tại ranh giới chịu trách nhiệm để giữ cause và stack trace.
- Chỉ chọn job/correlation ID được phép từ `params`. Không log toàn bộ đối số: chúng có thể chứa token, thông tin cá nhân hoặc object mutable.
- Handler có thể chạy trên worker, đồng thời với handler khác; dependency và bộ đếm phải thread-safe. Nếu recorder ghi I/O, xác định timeout, fallback và không block worker vô hạn.
- Exception sau một yêu cầu remote không chứng minh side effect đã rollback. Việc retry, ghi trạng thái FAILED hoặc reconciliation cần contract và transaction riêng.

Những quyết định này sẽ được kiểm chứng ở ví dụ `@Configuration` và test với Spring context trong các phần sau.

## 5. Cấu hình tối thiểu qua @Configuration và @EnableAsync

**Tệp `AsyncErrorConfig.java` — class cấu hình Spring, không có main độc lập:**

```java
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncErrorConfig implements AsyncConfigurer {

    @Bean("backgroundExecutor")
    public ThreadPoolTaskExecutor backgroundExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("background-");
        return executor;
    }

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (error, method, params) -> {
            System.err.println("Lỗi async tại "
                    + method.getName()
                    + ": " + error.getMessage());
        };
    }
}
```

Ở đây:

1. `@EnableAsync` kích hoạt cơ chế dùng `@Async` trong ApplicationContext tương ứng.
2. Bean `backgroundExecutor` là `ThreadPoolTaskExecutor` do Spring quản lý vòng đời, không cần tự gọi `initialize()` trong phương thức `@Bean`.
3. `getAsyncUncaughtExceptionHandler()` cung cấp handler, được Spring async interceptor dùng cho những exception chưa xử lý của method `@Async void`.
4. Class không override `getAsyncExecutor()`. Vì các method có thể chọn bean theo `@Async("backgroundExecutor")`, không cần cấu hình default ngay trong ví dụ.
5. Số worker và queue 2/4/16 chỉ để minh họa. Production phải tính theo tải, thời gian chờ và bộ nhớ, không phải hằng số dùng chung.

Một service dùng cấu hình:

```java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    @Async("backgroundExecutor")
    public void send(String jobId) {
        throw new IllegalStateException(
                "Không gửi được job " + jobId);
    }
}
```

Lời gọi đến `NotificationService.send(...)` cần đi **từ một bean khác qua Spring proxy**. Khi ấy handler nhận đúng `Method send`, argument `jobId` và `IllegalStateException`. Nếu muốn tái sử dụng, có thể trả `new ConsoleAsyncErrorHandler()` từ `getAsyncUncaughtExceptionHandler()` thay vì dùng lambda.

## 6. Demo đầy đủ Java 17 + Spring: handler cho void, Future cho method có kết quả

Ví dụ sau có **hai method đều ném exception**, nhưng chỉ một exception được gửi tới `AsyncUncaughtExceptionHandler`. Chương trình dùng `CountDownLatch` để in kết quả theo thứ tự có thể kiểm chứng, không dựa vào `Thread.sleep(...)`.

Yêu cầu: JDK 17 trở lên, Maven, Spring Framework 6.2.7 theo pom. Đây là dự án Maven nhỏ độc lập, không cần HTTP server.

### 6.1. Cấu trúc

```text
async-handler-demo/
├── pom.xml
└── src/main/java/lesson/AsyncHandlerDemo.java
```

### 6.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lesson</groupId>
    <artifactId>async-handler-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.7</version>
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
```

### 6.3. Tệp src/main/java/lesson/AsyncHandlerDemo.java

```java
package lesson;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncHandlerDemo {

    public static void main(String[] args)
            throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(Config.class)) {

            Tasks tasks = context.getBean(Tasks.class);

            tasks.failVoid("job-42");
            if (!Config.HANDLED.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Không nhận được tín hiệu handler");
            }
            System.out.println("Caller đã xác nhận handler chạy");

            CompletableFuture<String> result = tasks.failFuture();
            try {
                result.join();
            } catch (CompletionException error) {
                System.out.println("Future lỗi: "
                        + error.getCause().getMessage());
            }
        }
    }

    @Configuration
    @EnableAsync
    public static class Config implements AsyncConfigurer {
        static final CountDownLatch HANDLED = new CountDownLatch(1);

        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("lesson-");
            return executor;
        }

        @Bean
        public Tasks tasks() {
            return new Tasks();
        }

        @Override
        public AsyncUncaughtExceptionHandler
                getAsyncUncaughtExceptionHandler() {
            return (ex, method, params) -> {
                String jobId = String.valueOf(params[0]);
                System.out.println("Handler: " + method.getName()
                        + "(" + jobId + "): " + ex.getMessage());
                HANDLED.countDown();
            };
        }
    }

    public static class Tasks {
        @Async("lessonExecutor")
        public void failVoid(String id) {
            throw new IllegalStateException("lỗi void");
        }

        @Async("lessonExecutor")
        public CompletableFuture<String> failFuture() {
            throw new IllegalArgumentException("lỗi Future");
        }
    }
}
```

### 6.4. Chạy

Ở thư mục chứa pom:

```bash
mvn -q compile exec:java -Dexec.mainClass=lesson.AsyncHandlerDemo
```

Ba dòng in bởi **chính chương trình** trong điều kiện chạy bình thường:

```text
Handler: failVoid(job-42): lỗi void
Caller đã xác nhận handler chạy
Future lỗi: lỗi Future
```

Nếu runtime không lên lịch task trong vòng 5 giây thì chương trình chủ động ném lỗi timeout thay vì chờ vô hạn. Với môi trường chạy bình thường, thứ tự output được bảo đảm:

- `tasks.failVoid("job-42")` đi qua proxy `@Async`, method trả `void` nên exception trong worker đến handler.
- Handler in trước rồi mới gọi `HANDLED.countDown()`; main đợi chốt trước khi in dòng thứ hai.
- `tasks.failFuture()` có kiểu trả `CompletableFuture<String>`. Lỗi nằm trong Future, `join()` ném `CompletionException`; caller lấy `getCause().getMessage()` và in dòng cuối.
- Handler `void` **không** nhận một sự kiện lỗi bổ sung chỉ vì `failFuture()` ném exception.
- Context được đóng bởi `try-with-resources`; không gọi `shutdown()` tùy tiện trong service sử dụng bean executor chung.

Code này kiểm chứng **đường báo exception**, không minh họa tính bền vững hoặc retry. `CountDownLatch` chỉ là công cụ kiểm thử: nó không phải đối tượng `@Async void` tự trả về.

## 7. Handler mặc định hoạt động như thế nào?

Nếu không chỉ định handler tùy chỉnh, Spring xử lý exception chưa được bắt từ `@Async void` bằng cách ghi log thông qua handler mặc định, thường là `SimpleAsyncUncaughtExceptionHandler`. Theo tài liệu chính thức Spring, exception của method void không thể chuyển lại cho caller, vì vậy mặc định chỉ được ghi nhận.

Điểm dễ hiểu nhầm:

- **Có log không đồng nghĩa task đã được khôi phục**: handler không tự gọi lại nghiệp vụ.
- **Không có exception ở caller không đồng nghĩa task đã thành công**: worker có thể lỗi sau khi request đã trả về.
- **Dùng custom handler mà chỉ ghi một dòng `error.getMessage()`** thường làm mất stack trace, tên method hoặc correlation ID cần cho điều tra.
- **Không ghi log** trong custom handler có thể khiến lỗi hoàn toàn khó thấy nếu không có metrics, tracing và kho trạng thái khác.

Một handler production thường kết hợp structured logging, metric counter có nhãn nhóm lỗi phù hợp và cảnh báo theo ngưỡng. Với tác vụ quan trọng, nên có job ID và cơ chế lưu trạng thái thất bại, không chỉ phụ thuộc một câu log.

## 8. Lỗi nào handler không xử lý?

### 8.1. Lỗi từ Future hoặc CompletableFuture

`@Async` trả `CompletableFuture<T>` đưa lỗi về caller qua Future:

```java
@Async("backgroundExecutor")
public CompletableFuture<Integer> calculate(int x) {
    if (x < 0) {
        throw new IllegalArgumentException("x phải không âm");
    }
    return CompletableFuture.completedFuture(x * 2);
}
```

Caller:

```java
service.calculate(-1).whenComplete((value, error) -> {
    if (error != null) {
        System.err.println("Future thất bại: " + error);
    }
});
```

Hai đoạn trên là **các mảnh method/caller Spring**, không phải chương trình chạy độc lập. Trong `Future` cơ bản, `get()` báo lỗi qua `ExecutionException`; với `CompletableFuture.join()` thường qua `CompletionException`. Không chờ bằng `get()/join()` ngay ở HTTP request thread nếu mục tiêu là phản hồi không chặn.

Nếu nghiệp vụ không cần trả dữ liệu nhưng caller cần biết task đã hoàn tất/lỗi, dùng `CompletableFuture<Void>` thay vì `void`:

```java
@Async("backgroundExecutor")
public CompletableFuture<Void> saveAudit(String id) {
    auditRepository.save(id);
    return CompletableFuture.completedFuture(null);
}
```

Khi đó caller có handle để quan sát kết quả; `AsyncUncaughtExceptionHandler` không còn là kênh lỗi chính của method này. `auditRepository` là thành phần giả định do ứng dụng cung cấp.

### 8.2. Lỗi khi gửi việc hoặc sai cấu hình executor

Một pool có thể từ chối task mới khi đã đầy hoặc đóng. Với `ThreadPoolTaskExecutor`, trong cấu hình từ chối thông thường, caller có thể thấy `TaskRejectedException` từ lời gọi qua proxy. Task chưa chạy, vì vậy không thể mặc định chờ handler `void` nhận lỗi này.

```java
try {
    notificationService.send("job-9");
} catch (TaskRejectedException rejected) {
    // Trả lỗi quá tải hoặc có chính sách retry an toàn.
    throw rejected;
}
```

Mảnh mã này giả định đã import `org.springframework.core.task.TaskRejectedException` và có bean `notificationService`. Cần xử lý ở ranh giới nhận việc; nếu API trả HTTP 202 mà thực tế executor đã từ chối, đó là một lỗi hợp đồng.

Lỗi chọn bean executor không tồn tại theo `@Async("missingExecutor")`, lỗi khởi tạo ApplicationContext hoặc method khai báo kiểu trả về không được hỗ trợ cũng là vấn đề wiring/hợp đồng, không phải phương thức `void` đã chạy và ném lỗi thông thường.

### 8.3. Exception được bắt bên trong task

```java
@Async("backgroundExecutor")
public void work(String id) {
    try {
        process(id);
    } catch (ExpectedBusinessException known) {
        recordResult(id, known);
    }
}
```

Mảnh code này giả định `ExpectedBusinessException`, `process` và `recordResult` của ứng dụng. Vì exception đã được catch và không được ném lại, handler toàn cục **không** nhận nó. Đó có thể là chủ ý nếu công việc đã có cơ chế xử lý nghiệp vụ; nhưng không được lặng lẽ nuốt mọi lỗi rồi ghi nhận thành công.

## 9. AsyncConfigurer khởi tạo sớm và rủi ro dependency

Spring Javadoc nhấn mạnh cấu hình triển khai `AsyncConfigurer` có thể được khởi tạo sớm trong lúc bootstrap. Nếu configurer field-inject một bean có proxy hoặc quá nhiều dependency, bean ấy có thể được tạo chưa qua đầy đủ BeanPostProcessor như mong muốn.

Ví dụ cần cảnh giác:

```java
@Configuration
@EnableAsync
public class FragileConfiguration implements AsyncConfigurer {
    @Autowired
    private ErrorRecorder recorder;

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (ex, method, params) ->
                recorder.record(method.getName(), ex);
    }
}
```

Đây là **mảnh cấu hình có nguy cơ**, chưa độc lập vì `ErrorRecorder` là component ứng dụng. Khi recorder cần `@Transactional`, `@Async`, proxy hoặc phụ thuộc vòng, việc inject quá sớm dễ gây khó đoán.

Một lựa chọn trì hoãn truy cập dependency là `ObjectProvider<ErrorRecorder>`:

```java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class LazyAsyncConfiguration implements AsyncConfigurer {

    private final ObjectProvider<ErrorRecorder> recorderProvider;

    public LazyAsyncConfiguration(
            ObjectProvider<ErrorRecorder> recorderProvider) {
        this.recorderProvider = recorderProvider;
    }

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (error, method, args) -> {
            recorderProvider.getObject().record(
                    method.getName(), error);
        };
    }
}
```

Ví dụ này cần `ErrorRecorder` được khai báo trong dự án; không phải class Java chạy độc lập. Điểm quan trọng: **không gọi `recorderProvider.getObject()` ngay trong `getAsyncUncaughtExceptionHandler()`** nếu mục tiêu là hoãn khởi tạo. Chỉ lấy bean trong lúc handler thực sự xử lý lỗi, và vẫn phải kiểm soát lỗi thứ cấp/vòng gọi.

Nếu chỉ cần ghi log, handler stateless không phụ thuộc bean phức tạp là lựa chọn dễ kiểm thử và vận hành hơn.

## 10. Tùy chỉnh executor mặc định và handler là hai việc riêng

Cùng một class có thể override:

```java
@Override
public Executor getAsyncExecutor() {
    return defaultExecutor;
}

@Override
public AsyncUncaughtExceptionHandler
        getAsyncUncaughtExceptionHandler() {
    return customHandler;
}
```

Đây là **hai mảnh method minh họa**, với `defaultExecutor` và `customHandler` giả định đã được cấu hình đúng và thuộc vòng đời ứng dụng.

`getAsyncExecutor()` dùng để chỉ định **pool mặc định** cho những method `@Async` không chọn executor. `@Async("backgroundExecutor")` có thể chọn một bean executor cụ thể bằng tên/qualifier, kể cả khi default executor khác. Handler qua `getAsyncUncaughtExceptionHandler()` vẫn phục vụ lỗi của `@Async void` được xử lý bởi hạ tầng cùng context, không phải “chỉ bắt lỗi từ default pool”.

Nếu không cấu hình executor mặc định, Spring tìm theo quy tắc bean `TaskExecutor`/bean `taskExecutor`; nếu không tìm được phù hợp, có thể dùng `SimpleAsyncTaskExecutor`. Trong môi trường có nhiều executor, cần xác định rõ đường định tuyến và không dựa vào lựa chọn ngầm.

**Không tạo pool riêng trong handler chỉ để ghi log.** Handler chạy trong bối cảnh xử lý lỗi của một task; nếu cần đẩy telemetry đi nơi khác, phải có chính sách giới hạn tài nguyên, timeout và fallback. Dùng chung pool đang quá tải để đệ quy gửi thêm task ghi lỗi có thể làm tình hình xấu hơn.

## 11. Proxy và @EnableAsync: vì sao handler không chạy?

### 11.1. Gọi trong cùng bean (self-invocation)

```java
public void outer() {
    this.failAsync();  // Bỏ qua proxy ở chế độ mặc định.
}

@Async("backgroundExecutor")
public void failAsync() {
    throw new IllegalStateException("Lỗi");
}
```

Đây là phản ví dụ trong một class. Với proxy-based `@Async`, lời gọi `this.failAsync()` không đi qua interceptor nên Java thực thi method trực tiếp. Caller/`outer()` có thể thấy exception như lỗi đồng bộ. Handler của `@Async` không có cơ hội nhận lỗi.

Cách sửa phổ biến: đưa method async sang một bean khác, inject bean đó và gọi qua Spring-managed proxy. Không gọi method private/final và mong CGLIB proxy chặn mọi tình huống.

### 11.2. Tự tạo đối tượng bằng new

```java
new NotificationService().send("job-42");
```

Nếu đối tượng không được Spring quản lý, `@Async` chỉ là annotation ở source code; lời gọi không tự chuyển sang executor. Phải lấy bean do Spring quản lý từ context và bảo đảm `@EnableAsync` có hiệu lực đúng context.

### 11.3. Có nhiều ApplicationContext

Với ứng dụng có root context và servlet context, việc bật `@EnableAsync` trong một context không tự tạo proxy cho mọi bean ở context khác. Đặt cấu hình đúng nơi bean nghiệp vụ tồn tại và xác minh bằng integration test.

### 11.4. @Async method trả sai kiểu

Spring `@Async` thông thường hỗ trợ `void` hoặc kiểu `Future` như `CompletableFuture`. Chữ ký `@Async public String load()` là không hợp lệ cho async interceptor, không thể biến String đồng bộ thành kết quả nhận ngay. Lỗi kiểu trả về không phải lỗi từ thân method `@Async void` cần handler xử lý.

## 12. Xử lý lỗi handler thứ cấp

Handler được gọi khi tác vụ đã gặp sự cố. Nếu handler lại gọi database, network hoặc telemetry backend không khả dụng, bản thân handler có thể thất bại.

Spring có cơ chế ghi cảnh báo khi `AsyncUncaughtExceptionHandler` tự ném lỗi bất ngờ; nhưng caller của `@Async void` vẫn không có Future để nhận lỗi này, nên **không được xem đó là đường phục hồi đáng tin cậy**.

Một handler thực tế nên:

1. Ghi exception type, message, stack trace và method/operation đủ để điều tra.
2. Chỉ ghi những argument được phép, không log mật khẩu/token/payload đầy đủ.
3. Không lặp retry vô hạn hoặc gửi lại cùng công việc một cách mù quáng.
4. Có fallback logging/metrics tối thiểu nếu kho trạng thái không thể ghi.
5. Không làm các thao tác chờ vô hạn hoặc giữ khóa chung trong lúc gọi I/O.
6. Phân biệt lỗi nghiệp vụ đã dự kiến và lỗi hạ tầng để tránh cảnh báo sai.
7. Nếu cần lưu FAILED trạng thái job, thiết kế riêng transaction, khả năng ghi nhận và idempotency.

Một mẫu handler với fallback (mảnh method trong class có `logger` và `errorStore`):

```java
@Override
public void handleUncaughtException(
        Throwable error, Method method, Object... args) {
    String operation = method.getName();
    try {
        errorStore.markFailed(operation, error);
    } catch (RuntimeException reportingFailure) {
        logger.error("Async task thất bại: " + operation, error);
        logger.warn("Không ghi được trạng thái thất bại",
                reportingFailure);
    }
}
```

`errorStore` và `logger` ở đây là thành phần ứng dụng, không phải Java API có sẵn. Đừng dùng đoạn này như một class độc lập; nguyên tắc là **không để việc ghi nhận lỗi thứ cấp che khuất lỗi gốc**.

## 13. Log, metrics và bảo vệ dữ liệu

Một event lỗi có thể có các trường:

| Trường | Tại sao cần | Lưu ý |
|---|---|---|
| `operation`/`method` | Biết nghiệp vụ nào lỗi | Tên có cardinality hữu hạn |
| `exceptionType` | Phân loại lỗi kết nối/logic/timeout | Không chỉ in message |
| `jobId`/`correlationId` | Liên kết lần thực thi | Kiểm tra quyền ghi log |
| `executorName` | Khoanh vùng tài nguyên | Không nhất thiết suy từ thread name |
| `attempt` | Biết lượt thử khi có retry | Chống đếm trùng |
| `elapsed` | Phân biệt lỗi tức thời/chờ lâu | Cần đo queue wait riêng |
| `status` | Submitted/accepted/started/failed | Không đánh đồng accepted với succeeded |

Mẫu log **minh họa định dạng**, không phải output mặc định Spring:

```text
level=ERROR operation=sendNotification
jobId=J-102 exception=IllegalStateException
executor=backgroundExecutor message="Provider unavailable"
```

Nếu dùng Micrometer/Prometheus, một counter có thể mang nhãn operation và exception type. **Không đặt jobId làm tag metrics**, vì mỗi ID mới có thể tạo thêm time series, gây cardinality lớn. Job ID phù hợp hơn trong log/trace có chính sách dữ liệu riêng.

Handler chỉ ghi log không có nghĩa đã tạo job tracking. Nếu client cần xem `FAILED/SUCCEEDED` theo job ID, ứng dụng phải thiết kế kho trạng thái và giao diện truy vấn; không thể suy ra từ `AsyncConfigurer`.

## 14. Transaction, security và context không tự truyền

`@Async` thường chuyển thân method sang worker thread. Spring transaction gắn với caller không tự trở thành cùng transaction ở worker. Nếu worker gọi database và lỗi, handler không tự rollback transaction trước đó của caller.

```text
Request thread:
  @Transactional bắt đầu TX-A
  gửi @Async void job
  TX-A commit hoặc rollback theo chính sách caller

Worker thread:
  chạy độc lập về thời điểm
  nếu cần transaction thì thiết kế TX-B tại worker
  lỗi chưa xử lý -> AsyncUncaughtExceptionHandler
```

Nếu tác vụ nền đọc dữ liệu mà caller chưa commit, có thể thấy trạng thái cũ hoặc không thấy bản ghi, tùy transaction isolation. Với yêu cầu chỉ làm việc **sau commit**, cân nhắc transaction event/outbox hoặc cơ chế bảo đảm thời điểm gửi công việc.

`SecurityContextHolder`, MDC, custom `ThreadLocal` và request context không mặc nhiên được truyền đầy đủ sang worker khi dùng một executor bất kỳ. Nếu handler cần correlation ID, hãy truyền vào tham số task hoặc dùng context propagation được kiểm thử, và không giữ request object sau vòng đời.

**Handler không phải rollback của hệ thống ngoài**. Một email đã gửi hoặc tác vụ thanh toán đã thực hiện một phần có thể cần đối soát và bù trừ theo nghiệp vụ.

## 15. Khác với ExecutorService, @Scheduled và web exception handler

`AsyncUncaughtExceptionHandler` thuộc hạ tầng **Spring @Async**, không phải global exception handler cho JVM.

| Cơ chế | Kênh lỗi thông thường |
|---|---|
| `@Async void` qua Spring proxy | `AsyncUncaughtExceptionHandler` |
| `@Async Future<T>`/`CompletableFuture<T>` | Future/callback của caller |
| `ExecutorService.submit(...)` | Future mà `submit` trả |
| `ThreadPoolExecutor.execute(Runnable)` Java thuần | Theo worker/`UncaughtExceptionHandler` hoặc wrapper của task |
| `@Scheduled` | ErrorHandler/scheduler policy tương ứng |
| Spring MVC handler đồng bộ | Web exception resolvers/`@ControllerAdvice` theo cấu hình |
| Lỗi gửi vào pool bị từ chối | Caller/ranh giới submit, không mặc định void-handler |

Ví dụ `@Scheduled` có thể được cấu hình xử lý lỗi bởi `ErrorHandler` của Spring scheduling; không nên gắn `AsyncConfigurer` rồi mặc định rằng mọi tác vụ `@Scheduled` đều dùng cùng handler. Một ứng dụng có thể có cả `@Async` và `@Scheduled`, nhưng hai annotation biểu đạt đường thực thi khác nhau.

Nếu task có kết quả mà caller không quan sát Future, đó là **thiếu kiểm soát lỗi ở caller**; Spring không tự gửi exception đó sang void-handler chỉ vì Future bị bỏ quên.

## 16. Cách kiểm thử handler đúng, không dựa vào sleep

Một integration test nên dựng Spring context với `@EnableAsync`, bean executor có giới hạn và `AsyncConfigurer`. Gọi service qua proxy rồi dùng `CountDownLatch` hoặc callback để quan sát handler.

Một mảnh test JUnit (không độc lập, cần test context và assertions):

```java
CountDownLatch handled = new CountDownLatch(1);
AtomicReference<Throwable> observed = new AtomicReference<>();
AtomicReference<String> methodName = new AtomicReference<>();

AsyncUncaughtExceptionHandler testHandler = (error, method, args) -> {
    observed.set(error);
    methodName.set(method.getName());
    handled.countDown();
};

// Đăng ký testHandler qua AsyncConfigurer trong test context
// rồi gọi service Spring-managed:
service.failVoid("test-1");

assertTrue(handled.await(5, TimeUnit.SECONDS));
assertEquals("failVoid", methodName.get());
assertInstanceOf(IllegalStateException.class, observed.get());
```

Phải **thực sự đăng ký** `testHandler` vào `AsyncConfigurer` khi dựng context; việc chỉ tạo một biến handler trong test không làm Spring sử dụng nó. `AtomicReference`, `TimeUnit` và assertion methods cần import tương ứng. Với ví dụ độc lập đầy đủ, dùng `AsyncHandlerDemo` ở mục 6.

Những tình huống quan trọng:

1. `@Async void` ném exception: handler nhận đúng Throwable, Method, args.
2. `@Async void` thành công: handler không được gọi.
3. `@Async CompletableFuture` lỗi: Future báo lỗi; handler không có thêm lần gọi cho lỗi này.
4. Executor từ chối: caller quan sát rejection theo policy.
5. Self-invocation: chứng minh vì sao handler không nhận lỗi do advice không chạy.
6. Handler tự lỗi: fallback vẫn ghi được lỗi gốc ở mức phù hợp.
7. Tham số có thông tin nhạy cảm: không bị log toàn bộ.
8. Ứng dụng đóng/queue đầy: không tuyên bố task đã thành công nếu mới accepted.

`Thread.sleep(100)` không chứng minh worker hay handler đã chạy xong: trên CI/production, thời gian có thể dao động. Một tín hiệu hoàn tất có timeout là bằng chứng tốt hơn.

## 17. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| `AsyncConfigurer` tự xử lý mọi lỗi async | Chỉ cấu hình executor mặc định và handler không truyền lỗi được về caller của method void |
| Cấu hình handler xong là không cần xử lý lỗi Future | Future-typed method vẫn cần caller theo dõi |
| `try/catch` quanh caller bắt được mọi exception trên worker | Với async pool, lỗi thường đến sau khi caller đã trả |
| `@Async void` không thể gây exception vì return `void` | Exception runtime vẫn có thể ném ở thân method |
| Handler được gọi cả khi task chưa được executor nhận | Rejection là đường gửi, thường thuộc caller |
| `@EnableAsync` tự tạo thread pool production đúng tải | Cần định nghĩa/chọn executor và giới hạn tài nguyên |
| `this.asyncMethod()` kích hoạt Spring proxy | Self-invocation bỏ qua advice ở proxy mode mặc định |
| `Future` ném lỗi thì handler void cũng nhận | Exception nằm trong Future và phải được quan sát |
| Log handler có nghĩa nghiệp vụ đã retry | Logging không thực hiện retry/rollback |
| Handler có thể dùng mọi dữ liệu trong params để log | Cần bảo mật/ẩn dữ liệu và tránh payload lớn |
| `AsyncConfigurerSupport` là cách mới nhất | Deprecated từ Spring 6.0; implement interface trực tiếp |
| Handler ghi lỗi vào DB tự động dùng transaction caller | Worker/context có ranh giới khác; cần transaction riêng nếu phù hợp |
| Task đã accepted nghĩa là sẽ sống qua JVM crash | In-memory pool không phải hàng đợi bền vững |

## 18. Bài tập thực hành

### Bài 1 — Cấu hình handler đơn giản

Tạo class `@Configuration @EnableAsync implements AsyncConfigurer` trả một `AsyncUncaughtExceptionHandler`. Handler ghi tên method, exception class và mã job đã được phép. Tạo bean có `@Async("backgroundExecutor") void fail(String id)` ném `IllegalStateException`.

**Gợi ý:** Gọi từ bean khác qua Spring proxy, dùng latch để biết handler chạy. Không dùng `Thread.sleep` để đoán.

### Bài 2 — void khác Future

Hai method `void push()` và `CompletableFuture<String> load()` cùng ném lỗi. Handler của `AsyncConfigurer` nhận lỗi nào? Caller cần làm gì với lỗi còn lại?

**Gợi ý:** Handler nhận lỗi của `void`. Future chứa lỗi của `load()`; dùng `whenComplete`, `handle` hoặc `join/get` tại ranh giới chấp nhận chặn.

### Bài 3 — Lỗi gửi việc

Executor đã đầy, `@Async void` bị từ chối khi submit. Có được bảo đảm rằng handler sẽ ghi nhận không? Nếu API trả HTTP 202 trong khi job bị từ chối thì sai gì?

**Gợi ý:** Handler không tự bắt rejection; caller cần phản hồi quá tải đúng hợp đồng. HTTP 202 không được dùng để báo một công việc đã được nhận nếu thực tế bị từ chối.

### Bài 4 — Lazy dependency

Một `AsyncConfigurer` inject `ErrorRecorder` có `@Transactional` và cần proxy. Vì sao không nên lấy bean đó ngay trong quá trình bootstrap? Dùng `ObjectProvider` thế nào?

**Gợi ý:** Configurer được khởi tạo sớm; trì hoãn `getObject()` đến khi handler thực sự chạy, đồng thời bảo đảm không tạo vòng phụ thuộc.

### Bài 5 — Bảo mật và metrics

Handler nhận argument gồm mã job và token API. Bạn sẽ ghi những trường nào vào log, và vì sao không gắn mã job làm metric label?

**Gợi ý:** Log method, exception type, job ID được phép, correlation ID; che token. Metrics dùng nhãn có cardinality hữu hạn như operation, error type.

### Bài 6 — Handler tự lỗi

Handler ghi trạng thái FAILED vào database nhưng database đang lỗi. Caller có nhận được lỗi thứ cấp không? Hãy thiết kế fallback không che mất lỗi gốc.

**Gợi ý:** Caller của void async không có handle, không dựa vào exception truyền ngược; dùng logging fallback và quan sát trạng thái công việc riêng.

### Bài 7 — Chạy demo

Chạy `AsyncHandlerDemo` bằng lệnh Maven ở mục 6. Giải thích vì sao hai method đều ném lỗi nhưng chỉ có một dòng `Handler: ...`.

**Gợi ý:** `failVoid` gửi lỗi tới handler. `failFuture` gửi lỗi qua Future mà caller `join()` quan sát.

## 19. Checklist triển khai

Trước khi đưa handler `@Async` vào production:

1. `@EnableAsync` có hiệu lực ở context chứa bean; caller gọi qua Spring proxy.
2. Class cấu hình implement `AsyncConfigurer` và override đúng `getAsyncUncaughtExceptionHandler()`.
3. Handler ghi exception type/stack trace và method; không log secret hoặc nguyên payload.
4. Không nhầm exception của method `void` với Future-typed method hoặc lỗi gửi việc.
5. Executor có worker/queue giới hạn và rejection policy rõ ràng.
6. Không đưa cả request object hoặc thread-local nhạy cảm sang task/handler không có cơ chế propagation.
7. Nếu handler dùng bean khác, chú ý AsyncConfigurer khởi tạo sớm, ưu tiên dependency lazy khi cần.
8. Handler có fallback và không retry vô hạn, không chặn worker quá lâu.
9. Có correlation ID/job ID, phân biệt accepted/started/succeeded/failed.
10. Nếu nghiệp vụ yêu cầu chắc chắn thực hiện qua restart, sử dụng lưu trữ/hàng đợi bền vững.
11. Có integration test kiểm tra handler thật và Future error, không chỉ kiểm tra annotation có mặt.
12. Biết rằng handler không rollback transaction của caller hoặc side effect của hệ thống khác.

## 20. Điều cần nhớ

- **`AsyncConfigurer.getAsyncUncaughtExceptionHandler()`** là API chuẩn để cấu hình handler cho ngoại lệ không chuyển được về caller của method **`@Async void`**.
- Handler nhận **`Throwable`, `Method` và `Object... params`**, cần xử lý và ghi nhận một cách an toàn, không log dữ liệu nhạy cảm.
- **Future và CompletableFuture có kênh báo lỗi riêng**; đừng mong handler void nhận mọi lỗi bất đồng bộ.
- **Lỗi từ chối executor, sai cấu hình bean và self-invocation** có đường xử lý khác với exception của thân method đã chạy.
- **`@EnableAsync`, Spring-managed bean và lời gọi qua proxy** là điều kiện cốt lõi để handler được sử dụng đúng trong proxy mode.
- **Configurer có thể khởi tạo sớm**; tránh dependency phức tạp hoặc lấy bean proxy ngay trong quá trình bootstrap.
- **Handler không phải hệ thống retry/job queue bền vững.** Phải thiết kế quan sát trạng thái, idempotency, timeout và bù trừ theo yêu cầu nghiệp vụ.

### Tài liệu chính thức

- [Spring Framework Javadoc — AsyncConfigurer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html)
- [Spring Framework Javadoc — EnableAsync](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework Javadoc — AsyncUncaughtExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html)
- [Spring Framework Javadoc — SimpleAsyncUncaughtExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/SimpleAsyncUncaughtExceptionHandler.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Java SE 17 Javadoc — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
