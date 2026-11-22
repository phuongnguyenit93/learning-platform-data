# Chọn bộ thực thi mặc định bằng `AsyncConfigurer`

**Module:** Spring Framework - concurrency  
**Nhóm kiến thức:** Bật `@Async`  
**Trọng tâm:** Chủ động chọn executor dùng cho các phương thức `@Async` không chỉ rõ tên pool, phân biệt cấu hình mặc định với `@Async("beanName")`, quản lý vòng đời executor và xử lý ngoại lệ đúng cách.

## 1. Bài toán: `@Async` chạy ở pool nào?

Trong ứng dụng Spring, một phương thức được đánh dấu `@Async` có thể được Spring giao cho một executor để chạy ở thời điểm khác. Nhưng chỉ thêm annotation chưa trả lời được những câu hỏi vận hành rất quan trọng:

- Có bao nhiêu thread được phép chạy?
- Công việc đi vào queue nào, queue có giới hạn không?
- Tác vụ bị từ chối khi quá tải như thế nào?
- Một service chạy I/O chậm có chiếm hết worker của những service khác không?
- Nếu có nhiều executor bean, phương thức **không ghi tên executor** sẽ chọn cái nào?
- Lỗi trong phương thức trả `void` được xử lý ở đâu?

`AsyncConfigurer` là điểm mở rộng của Spring để cung cấp **executor mặc định** cho hạ tầng `@Async` và, nếu cần, **handler cho ngoại lệ của phương thức `@Async void`**.

```text
Lời gọi từ bean A -> Spring proxy của bean B
                         |
                         | @Async có tên executor?
                         |
              +----------+-----------+
              |                      |
         @Async("ioExecutor")     @Async
              |                      |
              v                      v
       Bean "ioExecutor"     AsyncConfigurer.getAsyncExecutor()
              |                      |
              +----------+-----------+
                         |
                   Executor đã chọn
                         |
                 Worker / queue / rejection
                         |
                      Hoàn tất
```

Cần phân biệt **chọn executor** với **bật cơ chế @Async**:

- `@EnableAsync` bật cơ chế phát hiện/intercept `@Async` trong **application context** tương ứng.
- `AsyncConfigurer` cung cấp lựa chọn mặc định khi lời gọi `@Async` **không** chỉ rõ một executor khác.
- `@Async("tenBean")` định tuyến riêng lời gọi đó đến bean executor có tên/qualifier tương ứng.
- Executor thực tế quyết định thread, queue, giới hạn nhận việc và cách từ chối. `AsyncConfigurer` **không** tự tạo một thread pool chỉ vì interface được implement.

## 2. Giao diện `AsyncConfigurer` cung cấp gì?

Trong Spring Framework 6.2, interface ở package `org.springframework.scheduling.annotation` có hai phương thức **default**:

```java
package org.springframework.scheduling.annotation;

// Phác thảo chữ ký, không phải mã nguồn đầy đủ của framework.
public interface AsyncConfigurer {
    default java.util.concurrent.Executor getAsyncExecutor() {
        return null;
    }

    default org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return null;
    }
}
```

Đây là **phác thảo để hiểu API**, không phải bản sao chính xác của source code Spring; hãy dùng interface có sẵn từ thư viện. Hai điểm mở rộng:

1. **`getAsyncExecutor()`** trả về `java.util.concurrent.Executor` mà Spring dùng làm mặc định cho `@Async` không chỉ định executor. Có thể trả `ThreadPoolTaskExecutor`, một `ExecutorService` của JDK hoặc implementation hợp lệ khác. Phương thức trả `null` thì Spring áp dụng cơ chế tìm executor mặc định bình thường.
2. **`getAsyncUncaughtExceptionHandler()`** trả về `AsyncUncaughtExceptionHandler` dùng khi phương thức `@Async` có kiểu trả về `void` ném ngoại lệ mà phía gọi không có `Future` để quan sát. Có thể trả `null` để dùng handler mặc định của Spring.

`AsyncConfigurer` **không** thay thế `@EnableAsync`, **không** điều khiển `@Scheduled`, không tự tạo durable queue và không đảm bảo context/transaction của thread gọi được truyền sang worker.

Vì Spring có cơ chế proxy để thực thi `@Async`, phương thức phải được gọi **qua Spring-managed proxy** trong chế độ mặc định `AdviceMode.PROXY`. Gọi nội bộ `this.doAsync()` không đi qua proxy nên annotation có thể bị bỏ qua.

## 3. AsyncConfigurer thay đổi điều gì so với lookup mặc định?

Nếu `AsyncConfigurer.getAsyncExecutor()` trả executor cụ thể, hạ tầng dùng nó cho lời gọi `@Async` **không chỉ định tên**. Nếu không có cấu hình mặc định phù hợp, Spring Framework tìm một bean `TaskExecutor` có thể chọn theo kiểu, sau đó xem bean `Executor` tên đúng `taskExecutor`, và cuối cùng có fallback `SimpleAsyncTaskExecutor`. Spring Boot có thể auto-configure executor theo các điều kiện riêng; phải xem context thực tế.

| Trường hợp | Executor được dùng |
| --- | --- |
| `@Async` không tên và AsyncConfigurer trả pool X | Pool X |
| `@Async("ioExecutor")` | Bean/qualifier `ioExecutor`, dù mặc định là X |
| AsyncConfigurer không trả executor | Lookup type/name rồi fallback của Framework khi cần |

Đây là ranh giới của **bài chọn mặc định bằng AsyncConfigurer**: không coi tên bean bất kỳ hay auto-configuration là bằng chứng pool nào được dùng. Khi có nhiều ứng viên, kiểm thử thực tế với thread-prefix/bean wiring; nội dung tra cứu theo kiểu/tên và các trường hợp mơ hồ được giải thích riêng trong bài về thuật toán tìm executor.

## 4. Mẫu cấu hình tối thiểu và điểm dễ sai về lifecycle

Mẫu theo tài liệu Spring:

```java
@Configuration
@EnableAsync
public class AsyncConfig implements AsyncConfigurer {

    @Override
    public Executor getAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("async-");
        executor.initialize();
        return executor;
    }
}
```

Đây là **đoạn class minh họa**; cần các import tương ứng:

```java
import java.util.concurrent.Executor;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
```

Điểm cần nhớ: `ThreadPoolTaskExecutor` được tạo trực tiếp trong method trên **không tự động là một Spring bean được quản lý đầy đủ** chỉ vì method nằm trong `@Configuration`. Việc gọi `initialize()` là cần thiết trong ví dụ tạo thủ công; bạn cũng phải tổ chức shutdown/lifecycle khi ứng dụng đóng.

**Cách ưu tiên với Spring-managed lifecycle:** thêm `@Bean` cho phương thức `getAsyncExecutor()` hoặc tạo một bean executor riêng rồi trả lại bean đó. Khi `ThreadPoolTaskExecutor` là bean do container quản lý, Spring tự gọi lifecycle khởi tạo và hủy; **không cần gọi `initialize()` thủ công**.

Đặc biệt, `AsyncConfigurer` có thể bị khởi tạo **sớm** trong quá trình bootstrap context. Nếu cấu hình phải dùng dependency Spring khác, hãy cân nhắc `ObjectProvider<T>` hoặc injection lazy và tránh khởi tạo sớm cả một đồ thị bean có proxy/post-processing. Đừng inject một service nghiệp vụ phức tạp vào configurer chỉ để tính số thread.

## 5. Ví dụ Spring Boot chạy được: mặc định, chỉ định pool và lỗi `void`

Ví dụ đầy đủ dưới đây dùng **Java 17+**, **Spring Boot 3.5.7** (Spring Framework 6.2.x) và Maven. Nó tạo:

- Một executor mặc định có tên `configuredAsyncExecutor`, thread name bắt đầu `default-`.
- Một executor khác có tên `ioExecutor`, thread name bắt đầu `io-`.
- Một service dùng `@Async` **không chỉ định tên**, và một method dùng `@Async("ioExecutor")`.
- Một method trả `CompletableFuture` bị lỗi, được quan sát từ future.
- Một method `@Async void` bị lỗi, được đưa vào `AsyncUncaughtExceptionHandler`.

Hai pool đều có queue hữu hạn. Chương trình main **đợi Future có chủ đích để kiểm chứng**, không lấy mẫu này làm API HTTP trả lời ngay.

### 5.1. Cấu trúc dự án

```text
async-configurer-demo/
├── pom.xml
└── src/main/java/com/example/asyncconfig/
    ├── AsyncConfigurerDemoApplication.java
    ├── AsyncConfiguration.java
    └── AsyncJobService.java
```

### 5.2. `pom.xml`

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
    <artifactId>async-configurer-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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

`spring-boot-starter-aop` cung cấp phần hỗ trợ proxy/AOP và các thành phần nền Spring cần thiết; không cần một web server để trình diễn `@Async`.

### 5.3. `src/main/java/com/example/asyncconfig/AsyncConfiguration.java`

```java
package com.example.asyncconfig;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfiguration implements AsyncConfigurer {

    // Chỉ để chương trình demo kiểm chứng handler void một lần.
    public static final CompletableFuture<String> VOID_FAILURE =
            new CompletableFuture<>();

    @Override
    @Bean("configuredAsyncExecutor")
    public Executor getAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("default-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(3);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("io-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (exception, method, parameters) ->
                VOID_FAILURE.complete(
                        method.getName() + ":"
                        + exception.getClass().getSimpleName());
    }
}
```

**Giải thích:**

- `@EnableAsync` kích hoạt proxy advice cho `@Async`.
- `getAsyncExecutor()` trả `Executor` mặc định. `@Bean("configuredAsyncExecutor")` biến executor thực tế thành bean do Spring quản lý, bao gồm `initialize` và `destroy` thích hợp.
- `ioExecutor()` tạo một bean thứ hai. Nó **không** tự thay thế lựa chọn mặc định, vì configurer đã trả pool `default-`.
- `VOID_FAILURE` là cầu nối quan sát lỗi dùng **một lần cho chương trình demo**, không phải hệ thống ghi nhận lỗi production. Ứng dụng thật dùng logger/metrics/tracing có context đầy đủ.
- `AbortPolicy` khiến lời giao task bị từ chối khi pool và queue không thể nhận nữa. `ThreadPoolTaskExecutor` thể hiện rejection theo contract của Spring (`TaskRejectedException`).
- Cấu hình core/max/queue chỉ để minh họa, phải điều chỉnh theo CPU, I/O, RAM, downstream và SLO thật.

### 5.4. `src/main/java/com/example/asyncconfig/AsyncJobService.java`

```java
package com.example.asyncconfig;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncJobService {

    @Async
    public CompletableFuture<String> defaultJob() {
        String thread = Thread.currentThread().getName();
        String pool = thread.startsWith("default-")
                ? "default" : "unexpected";
        return CompletableFuture.completedFuture(pool);
    }

    @Async("ioExecutor")
    public CompletableFuture<String> ioJob() {
        String thread = Thread.currentThread().getName();
        String pool = thread.startsWith("io-")
                ? "io" : "unexpected";
        return CompletableFuture.completedFuture(pool);
    }

    @Async
    public CompletableFuture<String> failedFutureJob() {
        throw new IllegalStateException("demo failure");
    }

    @Async
    public void failedVoidJob() {
        throw new IllegalArgumentException("demo void failure");
    }
}
```

Phương thức `defaultJob()` không có qualifier nên dùng pool do `AsyncConfigurer` trả về. `ioJob()` ghi rõ `"ioExecutor"` nên được giao cho pool riêng. Cả hai phương thức được gọi từ **bean khác** qua Spring proxy trong chương trình main.

Một phương thức có chữ ký `CompletableFuture<T>` trong implementation có thể trả `CompletableFuture.completedFuture(value)` để cung cấp kết quả do worker tính xong; phía gọi nhận future mà proxy cung cấp. Exception từ method `failedFutureJob()` làm future phía gọi hoàn thành lỗi; handler `AsyncUncaughtExceptionHandler` **không** phải nơi xử lý lỗi future đó.

### 5.5. `src/main/java/com/example/asyncconfig/AsyncConfigurerDemoApplication.java`

```java
package com.example.asyncconfig;

import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class AsyncConfigurerDemoApplication {

    public static void main(String[] args) throws Exception {
        SpringApplication app =
                new SpringApplication(AsyncConfigurerDemoApplication.class);

        // Chạy ở chế độ CLI, không mở HTTP server.
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.setDefaultProperties(Map.of("logging.level.root", "OFF"));

        try (ConfigurableApplicationContext context = app.run(args)) {
            AsyncJobService jobs = context.getBean(AsyncJobService.class);

            System.out.println("default=" +
                    jobs.defaultJob().get(5, TimeUnit.SECONDS));

            System.out.println("qualified=" +
                    jobs.ioJob().get(5, TimeUnit.SECONDS));

            try {
                jobs.failedFutureJob().get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                System.out.println("futureError=" +
                        ex.getCause().getClass().getSimpleName());
            }

            jobs.failedVoidJob();
            System.out.println("voidError=" +
                    AsyncConfiguration.VOID_FAILURE.get(
                            5, TimeUnit.SECONDS));
        }
    }
}
```

`try-with-resources` đóng Spring context sau khi demo xong; các executor dưới dạng bean được Spring quản lý theo lifecycle. `Future.get(timeout, unit)` ở đây **cố tình chờ** để output xác định và phát hiện lỗi, không đại diện cho lựa chọn hợp lý của một HTTP controller có deadline ngắn.

### 5.6. Chạy và quan sát

Điều kiện: đã cài JDK 17+ và Maven. Tại thư mục chứa `pom.xml`:

```bash
mvn -q spring-boot:run
```

**Các dòng `System.out` dự kiến khi chương trình hoàn tất bình thường:**

```text
default=default
qualified=io
futureError=IllegalStateException
voidError=failedVoidJob:IllegalArgumentException
```

Ứng dụng đã tắt Spring banner và logging của root logger trong ví dụ để tập trung vào kết quả. Nếu công cụ chạy/build hoặc môi trường in thêm dòng riêng, chỉ bốn dòng trên là output do main chủ động in. Thứ tự hoàn tất thật của worker có thể thay đổi, nhưng `main` đọc từng kết quả bằng future nên thứ tự bốn dòng `System.out` này là cố định.

**Tại sao đây là bằng chứng chọn đúng executor?**

1. `defaultJob()` chạy trên một thread có prefix `default-`; không phải bean `ioExecutor` dù trong context có hai pool.
2. `ioJob()` chạy trên thread prefix `io-`; qualifier của method thắng lựa chọn mặc định.
3. `failedFutureJob()` trả exception vào future; `Future.get()` ném `ExecutionException` và `getCause()` là `IllegalStateException`.
4. `failedVoidJob()` không có future để quan sát; handler của `AsyncConfigurer` nhận exception và hoàn thành `VOID_FAILURE` để main kiểm tra.

Không nên xây dựng logic production dựa trên **tên thread**. Prefix chỉ là cách trình diễn và debug; trong hệ thống thật, đo executor được chọn qua bean, task metrics và tracing.

## 6. Khi nào `@Async("...")` thay thế executor mặc định?

Mặc định từ `AsyncConfigurer` áp dụng cho **những lời gọi @Async không có executor qualifier**. Với qualifier, Spring định tuyến tới bean được chỉ định.

```java
@Service
public class ExportService {

    @Async
    public CompletableFuture<String> smallExport() {
        return CompletableFuture.completedFuture("small");
    }

    @Async("largeExportExecutor")
    public CompletableFuture<String> largeExport() {
        return CompletableFuture.completedFuture("large");
    }
}
```

Đây là **đoạn class minh họa** trong ứng dụng Spring: cần import `@Service`, `@Async`, `CompletableFuture` và có bean `"largeExportExecutor"` tồn tại. Nếu bean không tồn tại hoặc không tương thích với executor cần dùng, việc gọi có thể thất bại; Spring không nên âm thầm chọn một pool bất kỳ rồi che lỗi cấu hình.

Có thể đặt `@Async("defaultPool")` ở cấp class và chỉ định executor khác ở một method theo các quy tắc annotation; lựa chọn cụ thể của method thường ưu tiên hơn class-level. Hãy dùng tên bean/qualifier rõ ràng khi một service có nhiều loại tác vụ.

**Lưu ý:** `getAsyncExecutor()` không bắt mọi `CompletableFuture.supplyAsync(...)` hay `ExecutorService.submit(...)` tự viết trong code. Những lời gọi trực tiếp của JDK dùng executor được truyền cho chúng hoặc mặc định riêng của JDK, không tự tham chiếu Spring `AsyncConfigurer`.

## 7. Bắt đúng ngoại lệ: `void` và `Future` khác nhau

Spring cần một điểm xử lý lỗi khác nhau tùy chữ ký method:

| Return type của phương thức `@Async` | Bên gọi thấy gì? | Hướng xử lý lỗi |
| --- | --- | --- |
| `void` | Không có kết quả/future để chờ | `AsyncUncaughtExceptionHandler`, log/metric/alert |
| `Future<T>` | `Future` đại diện tác vụ | `get()` ném `ExecutionException` nếu task lỗi |
| `CompletableFuture<T>` | Có thể `get`, `join`, `whenComplete`, `handle` | Dùng completion stage và xử lý exceptional completion |
| Giá trị tùy ý như `String` | Không phải return type hỗ trợ cho `@Async` | Chuyển sang `void`/`Future`/`CompletableFuture` theo hợp đồng |

Ví dụ handler cho phương thức `void` trong ứng dụng thật:

```java
@Override
public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
    return (error, method, arguments) -> {
        log.error("Async void method {} failed",
                method.getName(), error);
        failedTaskCounter.increment();
    };
}
```

Đoạn trên **không phải chương trình độc lập**; `log` và `failedTaskCounter` là các dependency mà ứng dụng phải cung cấp. Các tham số method có thể chứa dữ liệu nhạy cảm; không tự log toàn bộ `arguments` khi chưa có chính sách bảo vệ.

Với `CompletableFuture`:

```java
CompletableFuture<Report> future = reportService.createReport(id);

future.whenComplete((report, error) -> {
    if (error != null) {
        recordFailure(id, error);
    } else {
        recordSuccess(id, report);
    }
});
```

Đây là đoạn minh họa có dependency `reportService`, `id`, kiểu `Report`, hai hàm ghi kết quả. `whenComplete` dùng để quan sát; bản thân callback ném lỗi cũng có cơ chế exceptional completion cần giám sát. Tránh bỏ mặc future của công việc quan trọng.

**Không kỳ vọng một exception từ worker được ném trực tiếp trở lại caller synchronous.** Exception xảy ra sau khi lời gọi `@Async` đã được giao cho executor; riêng lỗi **rejection khi giao việc** có thể xảy ra ngay tại thời điểm caller gọi method.

## 8. Vòng đời và khởi tạo sớm của `AsyncConfigurer`

### Hai cách cấp executor và trách nhiệm khác nhau

**Tạo thủ công trong `getAsyncExecutor()` (không `@Bean`):**

```java
@Override
public Executor getAsyncExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(10);
    executor.initialize();
    return executor;
}
```

Phải xác định ai sở hữu và đóng executor. Vì đối tượng không được quản lý đầy đủ bởi container, không tự giả định Spring gọi destroy. Nếu ứng dụng tạo nhiều object không kiểm soát, có thể rò thread.

**Trả Spring bean:**

```java
@Override
@Bean("configuredAsyncExecutor")
public Executor getAsyncExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(10);
    return executor;
}
```

Khi method thực sự được Spring đăng ký thành `@Bean`, bean lifecycle quản lý initialize/destroy và không cần gọi initialize thủ công. Đây cũng là cách mà ví dụ chạy hoàn chỉnh ở phần trên sử dụng.

### Nếu executor là bean được định nghĩa nơi khác?

Một số dự án cần đưa executor sang module cấu hình khác, hoặc sử dụng bean có decorator/monitoring phức tạp. `AsyncConfigurer` được khởi tạo sớm; tránh hard dependency gây vòng lặp bootstrap. Một cấu hình minh họa:

```java
@Configuration
@EnableAsync
class AsyncSetup implements AsyncConfigurer {
    private final ObjectProvider<Executor> executorProvider;

    AsyncSetup(
            @Qualifier("sharedAsyncExecutor")
            ObjectProvider<Executor> executorProvider) {
        this.executorProvider = executorProvider;
    }

    @Override
    public Executor getAsyncExecutor() {
        return executorProvider.getObject();
    }
}
```

Đây là **đoạn minh họa phụ thuộc vào Spring context**, cần import `java.util.concurrent.Executor`, `@Configuration`, `@EnableAsync`, `AsyncConfigurer`, `ObjectProvider`, `@Qualifier` và phải tồn tại bean `"sharedAsyncExecutor"`. `ObjectProvider` trì hoãn việc lấy bean đến khi cần, giúp tránh khởi tạo sớm dependency có proxy. Đừng tạo thêm nhiều `AsyncConfigurer` rời rạc để mỗi configurer chọn một pool khác nhau; lựa chọn mặc định là cấu hình ở cấp context, còn từng method có thể dùng qualifier.

### Chú ý khi shutdown

- `ThreadPoolTaskExecutor` là bean Spring có lifecycle; ứng dụng phải đóng context đúng cách.
- Các task đang chạy và nằm trong queue khi shutdown cần chính sách rõ: tiếp tục/chờ/cancel và deadline dừng; điều này phụ thuộc Spring version, cấu hình executor và container lifecycle.
- Không đóng pool ở cuối mỗi request nếu pool là shared bean.
- Bản thân việc có `AsyncConfigurer` không lưu task sang ổ đĩa/DB. Khi JVM chết, queue trong RAM có thể mất, kể cả bean lifecycle được quản lý tốt.
- Một Spring child context khác có thể không tự hưởng `@EnableAsync` của parent theo cách bạn hình dung; tài liệu nêu `@EnableAsync` áp dụng trong **local application context**.

## 9. Chọn pool kích thước bao nhiêu và từ chối thế nào?

`getAsyncExecutor()` trả `Executor`; cấu hình năng lực thực tế nằm ở executor đó. Với `ThreadPoolTaskExecutor`, ba tham số cốt lõi là:

| Tham số | Ý nghĩa | Sai lầm thường gặp |
| --- | --- | --- |
| `corePoolSize` | Số worker nền thường được duy trì theo cơ chế của pool | Đặt quá thấp rồi hy vọng `maxPoolSize` luôn được dùng |
| `maxPoolSize` | Trần worker có thể tạo khi tải và queue cho phép | Nghĩ rằng `max` đồng nghĩa số task sẽ chạy ngay |
| `queueCapacity` | Số task chờ, không tính task đang chạy | Đặt quá lớn khiến yêu cầu hết deadline nhưng vẫn nằm trong queue |

Với mô hình `ThreadPoolExecutor` phía dưới, khi đủ core workers, task thường **được xếp vào queue trước**; chỉ khi queue không nhận thêm, pool mới cố mở rộng đến `maxPoolSize`. Nếu pool và queue đều đầy, task bị từ chối.

Ví dụ khởi đầu cho hai loại công việc:

- **CPU-bound:** worker xấp xỉ ngân sách CPU khả dụng sau khi tính tải của JVM khác; pool cố định hoặc gần cố định; queue hữu hạn.
- **Blocking I/O:** có thể cần nhiều worker hơn số CPU vì nhiều thread đợi mạng/DB, nhưng còn bị giới hạn bởi connection pool, rate limit, timeout và RAM.
- **Tác vụ nghiệp vụ quan trọng:** cân nhắc job bền vững qua DB/queue/broker thay vì chỉ đẩy vào executor trong JVM.

Trong một ứng dụng có hai pool, hãy đặt **ngân sách tổng** theo tài nguyên. Việc `@Async` mặc định đi vào pool A và `@Async("ioExecutor")` đi vào pool B không làm CPU/DB connections tự tăng.

### Rejection khi quá tải

`ThreadPoolTaskExecutor` tuân theo ngoại lệ từ chối dạng `TaskRejectedException` của Spring. Với `AbortPolicy`, lời giao việc có thể thất bại ngay khi pool không còn sức chứa. Nếu một controller muốn báo “đã nhận xử lý”, cần phân biệt trường hợp giao việc thành công với trường hợp bị từ chối:

```java
try {
    reportService.submitAsync(id);
    // Chỉ phản hồi accepted nếu hợp đồng thực sự cho phép
    // nhận tác vụ vào bộ nhớ; durability phải được thiết kế riêng.
} catch (TaskRejectedException ex) {
    // Ánh xạ sang lỗi overload có chủ đích, chẳng hạn HTTP 503.
}
```

Đây là **đoạn minh họa**, có `reportService`, `id`, `TaskRejectedException` và response HTTP do ứng dụng định nghĩa. Nếu yêu cầu **không mất job sau restart**, dùng DB/broker bền vững trước khi trả `202`, thay vì coi `executor.execute(...)` là xác nhận durable.

`CallerRunsPolicy` của JDK có thể chạy task trên **thread gửi** khi pool từ chối, gây chặn HTTP thread. Vì vậy nếu cần fail fast, chọn rejection policy có chủ đích. `@Async` không đảm bảo chạy trên thread riêng trong mọi trường hợp nếu bạn chọn delegate hoặc policy có đặc tính chạy trực tiếp.

## 10. Các lỗi phổ biến khi chọn executor mặc định

| Lỗi | Hiện tượng | Cách kiểm tra/sửa |
| --- | --- | --- |
| Quên `@EnableAsync` | Gọi `@Async` vẫn xử lý trong thread caller | Bật trong đúng application context |
| Gọi `this.doAsync()` bên trong cùng bean | Bỏ qua proxy, không chuyển sang executor | Gọi qua Spring bean khác, thiết kế lại ranh giới |
| Có hai executor và không biết cái nào được chọn | Method không qualifier chạy vào pool khác kỳ vọng | Dùng `AsyncConfigurer` hoặc `@Async("beanName")`, kiểm tra bean thực tế |
| Tưởng `getAsyncExecutor()` cấu hình tất cả API bất đồng bộ | `CompletableFuture.supplyAsync` hoặc `@Scheduled` vẫn dùng tài nguyên khác | Truyền executor tường minh cho JDK API; cấu hình scheduler riêng |
| Dùng executor không có `@Bean`, cũng không gọi `initialize()` | Pool Spring chưa được khởi tạo đúng | Initialize và quản lý lifecycle thủ công, hoặc chuyển thành Spring bean |
| Khởi tạo `AsyncConfigurer` với dependency phức tạp/autowired sớm | Bean/proxy chưa sẵn sàng, lỗi bootstrap | Dùng lazy `ObjectProvider`, tách cấu hình rõ ràng |
| Tưởng `@Bean` return `Executor` làm mất lifecycle của `ThreadPoolTaskExecutor` | Lo lắng phải gọi initialize thêm | Bean thực tế vẫn là `ThreadPoolTaskExecutor`, Spring quản lý lifecycle |
| `@Async void` ném exception mà không có handler theo dõi | Caller không nhận được lỗi | Cài `AsyncUncaughtExceptionHandler`, log/metrics |
| `CompletableFuture` thất bại nhưng bị bỏ qua | Lỗi nền không ai quan sát | `whenComplete`/`handle`/`get`, trạng thái job |
| Tạo pool mới bên trong từng method/request | Rò thread, không có giới hạn toàn ứng dụng | Bean executor dùng chung, shutdown theo context |
| Queue không giới hạn, `maxPoolSize` rất lớn | Backlog tăng, max threads ít được dùng, OOM | Bounded queue, sizing và rejection policy |
| Chỉ test tên thread mà không có kiểm thử hành vi | Không phát hiện lỗi overload/exception/timeout | Test loại executor, số task đang chạy, rejection và shutdown |
| Copy transaction/request context qua ThreadLocal tùy tiện | Đọc dữ liệu chưa commit, rò security context | Worker tự mở transaction; truyền ID/dữ liệu rõ ràng và cleanup đúng |
| Đưa CPU-heavy task vào pool I/O, hoặc ngược lại | Starvation, p99 không ổn định | Phân pool theo tài nguyên, đo thực tế |

## 11. Kiểm thử cấu hình trong dự án thật

**Kiểm thử chức năng tối thiểu:**

1. Bật `@EnableAsync` trên một config class được component scan.
2. Implement `AsyncConfigurer` và trả executor được cấu hình có `threadNamePrefix` phân biệt.
3. Gọi một method public `@Async` **qua bean khác** và xác minh nó dùng pool được configurer trả.
4. Định nghĩa một bean executor thứ hai; dùng `@Async("otherExecutor")` và xác minh qualifier chọn đúng pool.
5. Bật nhánh lỗi `void` và kiểm tra `AsyncUncaughtExceptionHandler` nhận exception.
6. Bật nhánh lỗi `CompletableFuture` và kiểm tra exceptional completion.
7. Cho queue đầy bằng `CountDownLatch`, kiểm tra rejection/response thay vì dùng `Thread.sleep` để đoán race.
8. Đóng context để kiểm tra không còn thread rò, xử lý đúng các task còn chạy.

**Kiểm thử vận hành:** dưới tải thật, đo active threads, queue depth, queue wait, task execution time, reject count, p95/p99 latency, CPU throttling, JDBC/HTTP connections và startup/shutdown. Cấu hình đúng API chưa đồng nghĩa cấu hình năng lực đúng workload.

**Tình huống cần đo riêng:** khi đã bật `@Async`, controller có thể nhận được `CompletableFuture` nhưng vẫn chặn request nếu gọi `.get()`/`.join()` ngay. Nếu mục tiêu là giải phóng Servlet thread **mà giữ một response đang chờ kết quả**, dùng cơ chế async request của Spring MVC phù hợp. Nếu muốn trả `202 Accepted` và xử lý dài sau, cần API job/status/durability riêng.

## 12. Câu hỏi tự kiểm tra

**1.** Có hai `ThreadPoolTaskExecutor` bean `"cpuExecutor"` và `"ioExecutor"` nhưng muốn mọi method `@Async` không qualifier mặc định dùng `"cpuExecutor"`. Chọn gì?  
**Đáp:** Implement `AsyncConfigurer.getAsyncExecutor()` trả bean cpuExecutor (hoặc cấu hình ứng dụng có quy tắc mặc định rõ ràng). Những method cần pool I/O dùng `@Async("ioExecutor")`.

**2.** `getAsyncExecutor()` bắt buộc trả `ThreadPoolTaskExecutor` không?  
**Đáp:** Không, return type là `java.util.concurrent.Executor`; implementation có thể là executor JDK hoặc loại phù hợp khác, miễn đáp ứng contract/nhu cầu vận hành.

**3.** Vì sao thêm `@Bean` vào `getAsyncExecutor()` có ý nghĩa?  
**Đáp:** Executor trả về trở thành bean Spring; lifecycle initialization/destroy được container quản lý nếu là loại hỗ trợ lifecycle như `ThreadPoolTaskExecutor`.

**4.** Phương thức `@Async("ioExecutor")` có dùng executor trả từ `AsyncConfigurer` không?  
**Đáp:** Thường không. Giá trị chỉ định tên/qualifier trên `@Async` yêu cầu bean tương ứng và thay thế lựa chọn mặc định cho lời gọi đó.

**5.** `@Async void` ném `IllegalArgumentException` thì caller có bắt được bằng `try/catch` quanh lời gọi không?  
**Đáp:** Không theo cách thông thường khi task thực thi trên worker sau đó; handler `AsyncUncaughtExceptionHandler` nhận lỗi. Ngoại lệ ngay lúc **giao task**, như rejection, là tình huống khác.

**6.** `@Async CompletableFuture<String>` thất bại; handler dành cho `void` có bắt không?  
**Đáp:** Không. Bên gọi phải quan sát future hoàn thành lỗi qua `get()`, `whenComplete` hoặc cơ chế tương đương.

**7.** `this.generate()` có `@Async` nhưng vẫn chạy synchronous; sai ở đâu?  
**Đáp:** Self-invocation bỏ qua proxy trong `AdviceMode.PROXY` mặc định.

**8.** Vì sao có `maxPoolSize=32` mà chỉ thấy bốn worker chạy khi queue chưa đầy?  
**Đáp:** `ThreadPoolExecutor` thường xếp queue sau core trước khi tạo worker vượt core. Cần hiểu `corePoolSize`, `queueCapacity` và deadline.

**9.** Có nên cho `AsyncConfigurer` tự tạo `new ThreadPoolTaskExecutor()` ở mỗi lần xử lý request không?  
**Đáp:** Không. Executor dùng chung trong context với một cấu hình và lifecycle rõ ràng; request chỉ gửi task vào executor.

**10.** `getAsyncExecutor()` bảo đảm job được xử lý sau khi JVM restart?  
**Đáp:** Không. Đây là lựa chọn executor thực thi trong JVM. Durability cần persistence/queue/broker và recovery.

## 13. Ghi nhớ

`AsyncConfigurer` giúp **chọn minh bạch executor mặc định cho `@Async`** và cung cấp handler cho **ngoại lệ của phương thức `void`**. Cấu hình tác động đến lời gọi đi qua Spring async advice trong context tương ứng; `@Async("beanName")` có thể chỉ định pool riêng.

- **Bật:** `@EnableAsync`.
- **Chọn mặc định:** implement `AsyncConfigurer.getAsyncExecutor()`.
- **Chọn riêng:** `@Async("ioExecutor")`.
- **Xử lý lỗi:** `getAsyncUncaughtExceptionHandler()` cho `void`; `Future`/`CompletableFuture` được quan sát bởi caller hoặc job orchestration.
- **Quản lý vòng đời:** ưu tiên executor là Spring bean, queue có giới hạn và shutdown theo context.
- **Xác minh:** gọi qua Spring proxy, đo thread/queue/rejection, thử nghiệm dưới tải và ghi rõ hợp đồng khi job phải sống sau HTTP.

**Tài liệu chính thức:**

- [Spring Framework 6.2 — `@EnableAsync` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): quy tắc tìm executor, ví dụ `AsyncConfigurer`, vòng đời, proxy.
- [Spring Framework 6.2 — `AsyncConfigurer` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html): hai method cấu hình và lưu ý init sớm.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): abstraction, `@Async`, executor, exception handling.
- [Spring Framework 6.2 — `ThreadPoolTaskExecutor`](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): cấu hình và lifecycle pool.
- [Java SE 17 — `Executor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): contract gốc của JDK.