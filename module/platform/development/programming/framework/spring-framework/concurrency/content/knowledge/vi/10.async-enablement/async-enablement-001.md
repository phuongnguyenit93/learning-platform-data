# Khai báo @EnableAsync trong lớp cấu hình

## 1. Mục tiêu của bài học

Trong Spring Framework, thêm `@Async` vào một phương thức **chưa đủ** để khẳng định lời gọi được chạy bất đồng bộ. Ứng dụng phải bật cơ chế xử lý annotation async trong **Spring application context**. Cách khai báo phổ biến là đặt `@EnableAsync` trên một lớp `@Configuration`.

Sau bài học, bạn cần làm được các việc:

1. Khai báo đúng `@Configuration` + `@EnableAsync` và các import cần thiết.
2. Giải thích thứ gì được bật: hạ tầng intercept `@Async`, **không phải** một lời hứa tạo thread pool có giới hạn.
3. Định nghĩa bean `ThreadPoolTaskExecutor` và chỉ định bean đó bằng `@Async("...")`.
4. Hiểu tại sao phải gọi phương thức qua Spring-managed proxy; nhận diện self-invocation, đối tượng tự `new` và giới hạn proxy.
5. Phân biệt cấu hình tối thiểu, cấu hình mặc định của Spring Framework và hỗ trợ auto-configuration có điều kiện của Spring Boot.
6. Nhận đúng `Future`/`CompletableFuture`, xử lý exception, kiểm soát thread và vòng đời.
7. Chạy một ví dụ Java 17+ có thể biên dịch, và xác minh rằng phương thức thực sự được thực thi trong executor được chỉ định.

**Phạm vi:** bài tập trung vào hành động **khai báo `@EnableAsync` trong lớp cấu hình** và điều kiện để khai báo này có tác dụng; không biến nó thành bài tổng quan về mọi mô hình concurrency hoặc lập lịch.

## 2. Cấu hình tối thiểu của Spring Framework

`@EnableAsync` nằm trong package `org.springframework.scheduling.annotation`. `@Configuration` nằm trong `org.springframework.context.annotation`.

Ví dụ tối thiểu:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfig {
}
```

Đây là một lớp cấu hình hợp lệ khi nó được **đăng ký vào Spring application context** (qua component scanning, `@Import`, hoặc đăng ký trực tiếp). Riêng đoạn mã này chưa phải một chương trình độc lập: cần một application context và các bean chứa phương thức `@Async`.

Tác dụng của từng annotation:

- `@Configuration` cho Spring biết lớp này cung cấp cấu hình bean; thường kết hợp với các method `@Bean`.
- `@EnableAsync` import hạ tầng hỗ trợ asynchronous method execution. Trong chế độ mặc định `PROXY`, Spring đăng ký các thành phần thích hợp để intercept các phương thức được đánh dấu `@Async` trên **bean được Spring quản lý**.
- `@Async` được đặt lên method hoặc class cần chạy bất đồng bộ; invocation thích hợp sẽ được chuyển thành task cho executor.
- Việc **bật xử lý annotation** và **chọn executor thực sự** là hai trách nhiệm riêng.

Không cần đặt `@EnableAsync` trên mọi service. Thông thường một lớp cấu hình được nạp trong context thích hợp là đủ để kích hoạt cơ chế cho các bean thuộc context đó.

### 2.1. Hình dung luồng gọi

```text
Spring ApplicationContext
   |
   +-- nhận lớp @Configuration + @EnableAsync
   |         |
   |         +-- đăng ký hạ tầng async/proxy
   |
   +-- quản lý WorkService bean
   |         |
Caller --> Spring proxy --> @Async interceptor
                              |
                              +-- chọn Executor
                              |
                              +-- submit task
                                      |
                                      +-- thực thi method ở worker thread
                                      |
                                      +-- hoàn thành Future/CompletableFuture
```

Hình vẽ mô tả đường gọi khi proxy hoạt động bình thường. Một lời gọi không đi qua proxy, chẳng hạn `this.work()` trong chính bean, không tự nhiên trở thành bất đồng bộ chỉ vì method có annotation.

### 2.2. Vì sao ứng dụng cần cả hai thành phần?

Hai đoạn sau không tương đương:

```java
// Chỉ khai báo method: chưa chứng minh async infrastructure được bật.
@Async
public CompletableFuture<String> work() {
    return CompletableFuture.completedFuture("ok");
}
```

```java
// Bật hạ tầng cho context chứa các bean phù hợp.
@Configuration
@EnableAsync
class AsyncConfig {
}
```

Một cấu hình `@EnableAsync` không làm **mọi** method trong ứng dụng tự chạy async. Chỉ những lời gọi phù hợp với annotation và interception mới được điều phối. Ngược lại, nếu method có `@Async` nhưng context không bật async, annotation thường không đổi hành vi lời gọi trong cấu hình Framework thông thường.

## 3. Ví dụ hoàn chỉnh: tạo cấu hình, executor và service

Bản mẫu sau dùng **Java 17+, Spring Framework 6.2.14 và Maven**; chạy độc lập mà không cần Spring Boot. Nó khai báo `@EnableAsync` trên lớp cấu hình, tạo executor hữu hạn và thực hiện một lời gọi qua Spring-managed bean.

Cấu trúc thư mục:

```text
enable-async-demo/
├── pom.xml
└── src/main/java/demo/EnableAsyncDemo.java
```

### 3.1. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>enable-async-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.14</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 3.2. Tệp EnableAsyncDemo.java

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

public class EnableAsyncDemo {
    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AsyncConfig {
        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setThreadNamePrefix("lesson-worker-");
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(4);
            executor.setQueueCapacity(16);
            return executor;
        }

        @Bean
        public ReportService reportService() {
            return new ReportService();
        }
    }

    public static class ReportService {
        @Async("lessonExecutor")
        public CompletableFuture<Boolean> onWorker(String callerThread) {
            String current = Thread.currentThread().getName();
            boolean result =
                    current.startsWith("lesson-worker-")
                    && !current.equals(callerThread);
            return CompletableFuture.completedFuture(result);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AsyncConfig.class)) {
            ReportService service = context.getBean(ReportService.class);
            String callerThread = Thread.currentThread().getName();

            CompletableFuture<Boolean> result =
                    service.onWorker(callerThread);

            System.out.println("async-on-configured-pool="
                    + result.get(5, TimeUnit.SECONDS));
        }
    }
}
```

### 3.3. Biên dịch và chạy

Tại thư mục chứa `pom.xml`:

```bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.EnableAsyncDemo
```

Kết quả từ dòng `System.out.println` trong điều kiện bình thường:

```text
async-on-configured-pool=true
```

Maven hoặc môi trường có thể in thêm thông báo. Ví dụ cố ý kiểm tra **thread name** thay vì suy đoán từ thời gian chạy; `result.get(5, TimeUnit.SECONDS)` đợi kết quả tối đa năm giây và trả lỗi nếu task thất bại hoặc quá thời gian.

### 3.4. Giải thích từng bước

1. `AnnotationConfigApplicationContext` đăng ký lớp `AsyncConfig`, tức lớp chứa `@Configuration` và `@EnableAsync` đã thực sự được Spring nạp.
2. Bean `lessonExecutor` là `ThreadPoolTaskExecutor`. Các giá trị core=2, max=4, queueCapacity=16 chỉ minh họa một pool hữu hạn, không phải cấu hình chung tối ưu cho mọi tải.
3. Bean `reportService` được Spring tạo. Khi cần, Spring áp dụng async proxy cho phương thức `onWorker(...)`.
4. Client lấy bean từ context, **không** gọi `new ReportService()`, vì object tự tạo sẽ không nhận interception.
5. `@Async("lessonExecutor")` chỉ rõ tên executor được chọn thay vì dựa vào lookup mặc định.
6. Worker lấy tên thread đang chạy method. Prefix `lesson-worker-` cùng việc thread khác caller xác nhận đường chạy dự kiến.
7. Method trả `CompletableFuture.completedFuture(...)` ở **bên trong worker**. Interceptor cung cấp future cho caller để theo dõi hoàn tất.
8. Khi đóng context, Spring quản lý lifecycle của bean executor đã đăng ký; code caller không tự gọi `shutdown()` trên executor dùng chung giữa các service.

Nếu đổi `@Async("lessonExecutor")` thành `@Async`, cần xem quy tắc chọn executor mặc định của context. Nếu xóa `@EnableAsync` và không có cấu hình async khác, lời gọi có thể chạy trực tiếp trên caller thread; khi đó phép kiểm tra prefix sẽ thất bại.

## 4. Khai báo trong ứng dụng Spring Boot

Spring Boot dùng Spring Framework làm nền. Trong một ứng dụng Boot, bạn có thể đặt `@EnableAsync` trực tiếp trên lớp main hoặc trong một lớp `@Configuration` riêng.

### 4.1. Trên lớp main

Đây là **fragment ứng dụng Spring Boot**, cần Spring Boot dependencies, không phải chương trình độc lập chỉ bằng `javac`:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

`@SpringBootApplication` không phải cách viết đồng nghĩa với `@EnableAsync`. Thông thường, bạn vẫn phải bật async annotation processing có chủ đích khi muốn dùng `@Async`. Boot có thể tạo executor mặc định bằng auto-configuration **có điều kiện**, nhưng **có executor** và **bật annotation interceptor** là hai việc khác nhau.

### 4.2. Trên một lớp cấu hình riêng

Phương án phù hợp khi muốn tách cấu hình concurrency khỏi điểm khởi động:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncInfrastructureConfig {
}
```

Cần bảo đảm `AsyncInfrastructureConfig` nằm trong phạm vi component scan hoặc được import vào context:

```java
@SpringBootApplication
@Import(AsyncInfrastructureConfig.class)
public class Application {
    // Các import và phương thức main được khai báo trong project.
}
```

Đây cũng là fragment; `@Import` là lựa chọn khi cấu hình không được component scan nạp. **Không** đặt cùng cấu hình nhiều nơi nếu điều đó làm người đọc nhầm context hoặc tạo bean trùng lặp. Với ứng dụng có nhiều context (ví dụ parent và child), `@EnableAsync` có hiệu lực ở context nơi nó được khai báo; không suy ra tự động bao phủ mọi context con.

### 4.3. Boot tự cấu hình executor không có nghĩa tự cấu hình mọi bean tùy chỉnh

Một project Spring Boot có thể dùng các thuộc tính như:

```yaml
spring:
  task:
    execution:
      thread-name-prefix: app-async-
      pool:
        core-size: 4
        max-size: 8
        queue-capacity: 64
```

Những thuộc tính đó áp dụng khi loại **Boot-managed executor** tương ứng thực sự được auto-configure và các điều kiện phù hợp. Nếu bạn khai báo `@Bean("lessonExecutor") ThreadPoolTaskExecutor` và đặt setter trực tiếp, Boot không tự buộc bean tùy chỉnh này nhận mọi giá trị `spring.task.execution.*`. Thêm bean `Executor` tùy chỉnh còn có thể ảnh hưởng điều kiện để Boot tạo executor mặc định; hãy xác minh danh sách bean theo đúng phiên bản Boot.

Kết luận của phần này: trong **Spring Framework thuần** hoặc **Spring Boot**, `@EnableAsync` vẫn làm nhiệm vụ **bật async interception**. Boot chỉ bổ sung hệ thống auto-configuration tài nguyên thực thi với các mặc định có điều kiện.

## 5. @EnableAsync thực sự bật cơ chế nào?

Trong chế độ phổ biến `AdviceMode.PROXY`, việc bật hỗ trợ sẽ đăng ký hạ tầng async advisor/interceptor và post-processor thích hợp. Khi một bean được quản lý có phương thức được nhận diện là async, lời gọi **qua proxy** sẽ được intercept trước khi chạy logic thật.

Các khái niệm cần phân biệt:

| Khái niệm | Vai trò |
| --- | --- |
| `@Configuration` | Định nghĩa lớp cấu hình Spring |
| `@EnableAsync` | Kích hoạt xử lý annotation async cho context |
| `@Async` | Đánh dấu method/class mà lời gọi phù hợp cần điều phối bất đồng bộ |
| `AsyncConfigurer` | Tùy chỉnh executor mặc định và handler exception của method async trả `void` |
| `@Async("executorName")` | Chọn executor bằng tên bean hoặc qualifier |
| `ThreadPoolTaskExecutor` | Một implementation executor quản lý worker/queue |
| `CompletableFuture<T>` | Handle quan sát trạng thái hoàn thành và kết quả của lời gọi async |
| Spring AOP proxy | Lớp trung gian cần thiết trong advice mode mặc định |
| `AdviceMode.ASPECTJ` | Chế độ weaving nâng cao; yêu cầu setup AspectJ bổ sung |

Đừng nhầm `@EnableAsync` với `@EnableScheduling`: cái thứ nhất phục vụ `@Async`, cái thứ hai phục vụ các method `@Scheduled`. Nếu ứng dụng cần cả hai, có thể khai báo cả hai trên một lớp cấu hình, nhưng chúng bật hai loại xử lý annotation khác nhau.

### 5.1. Vì sao gọi qua proxy quan trọng?

Trong chế độ mặc định, Spring thường tạo proxy bao quanh bean async. Với method phù hợp, caller gọi **proxy**, proxy submit task vào executor, sau đó method gốc chạy trong worker.

```text
Bean A ---> proxy(Bean B) ---> executor.submit ---> Bean B.work()
Bean B ---> this.work() ---------------------------> Bean B.work()
              (không qua proxy)
```

Dòng thứ hai là **self-invocation**: method trong chính Bean B gọi method khác của cùng instance bằng `this`, bỏ qua proxy trong mặc định `PROXY`. Do đó, dù method đích có `@Async`, nó có thể chạy đồng bộ trên thread hiện tại.

Các cách giải quyết thích hợp:

- **Ưu tiên:** tách phương thức async sang bean khác, inject và gọi qua Spring-managed bean.
- Có thể thiết kế caller dùng service interface/proxy nếu phù hợp cấu trúc dự án.
- Với nhu cầu đặc thù, cân nhắc mode AspectJ có weaving phù hợp; đó là thiết lập riêng, không chỉ đổi enum là xong.
- Không gợi ý tự inject chính mình như giải pháp mặc định, vì dễ gây vòng phụ thuộc và làm API khó hiểu.

### 5.2. Bean nào đủ điều kiện được xử lý?

Phương thức async nên là một method được gọi qua Spring-managed proxy. Cần kiểm tra:

- **Đối tượng có thuộc container không?** `new MyService()` do application tự tạo không được Spring tự áp dụng proxy.
- **Lời gọi có đi qua proxy không?** `this.method()` thường không.
- **Proxy có thể intercept method không?** Với class-based proxy, private/final method có giới hạn; method public là cách rõ ràng và ít rủi ro nhất cho bài học.
- **Annotation có nằm ở nơi framework nhận diện không?** Đặt trên method/class thực thi phù hợp; nếu dùng interface/proxy, kiểm tra theo cấu trúc thực tế.
- **Context có bật async không?** `@EnableAsync` phải được nạp trong đúng application context.

Không nên kết luận “Spring bỏ qua `@Async`” chỉ vì không thấy log thread mới: còn phải xem executor đã chọn, invocation path và giới hạn phương thức.

## 6. Những thuộc tính quan trọng của @EnableAsync

Cú pháp thông thường không cần đối số:

```java
@Configuration
@EnableAsync
public class AsyncConfig {
}
```

Với yêu cầu nâng cao, annotation cho phép điều chỉnh cách áp dụng advice:

| Thuộc tính | Ý nghĩa | Khuyến nghị khi học |
| --- | --- | --- |
| `mode` | Cách áp dụng async advice: `PROXY` (mặc định) hoặc `ASPECTJ` | Dùng `PROXY` trừ khi đã có lý do và hạ tầng weaving |
| `proxyTargetClass` | Với `PROXY`, ưu tiên class-based proxy thay vì interface-based proxy | Không bật bừa bãi; có tác động lên các proxy khác trong context |
| `order` | Thứ tự đăng ký post-processor/advisor async trong chuỗi proxy | Giữ mặc định nếu không có nhu cầu AOP phối hợp đặc biệt |
| `annotation` | Chỉ định loại annotation async tùy chỉnh ngoài các annotation mặc định | Chỉ cần ở hệ thống có convention riêng |

Ví dụ minh họa cấu hình tường minh chế độ mặc định:

```java
import org.springframework.context.annotation.AdviceMode;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync(mode = AdviceMode.PROXY, proxyTargetClass = false)
public class AsyncConfig {
}
```

Đây là một **fragment lớp cấu hình**; không phải yêu cầu bắt buộc phải viết `mode`/`proxyTargetClass`. Giá trị mặc định đã tương đương. Lưu ý việc Boot hoặc một cơ chế AOP khác có thể chọn loại proxy theo cấu hình của nó; không dùng thuộc tính này để suy ra chắc chắn object cuối cùng là JDK proxy hay class proxy trong mọi ứng dụng.

### 6.1. Khi nào cần AspectJ?

`@EnableAsync(mode = AdviceMode.ASPECTJ)` chỉ có ý nghĩa khi cấu hình đầy đủ AspectJ weaving và các dependency cần thiết. Nó có thể xử lý trường hợp local invocation mà proxy bỏ qua, nhưng tăng độ phức tạp build/runtime và có yêu cầu môi trường riêng. Đừng bật chỉ để sửa một self-invocation đơn giản; tách bean là giải pháp dễ hiểu và dễ test hơn.

## 7. Khai báo executor cùng lớp cấu hình

`@EnableAsync` chỉ bật xử lý; executor quyết định thread, queue, giới hạn tải và vòng đời. Với ứng dụng cần kiểm soát, khai báo một bean `ThreadPoolTaskExecutor`:

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfig {
    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("io-task-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(50);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
```

Đây là **fragment cấu hình Spring**, không phải chương trình độc lập. Các số 4/8/50/20 là ví dụ để hiểu cấu trúc; phải đo tải thật, CPU, downstream connection limit, deadline và thời gian chờ để chọn trong production.

Để gắn một method với pool này:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class EmailService {
    @Async("ioExecutor")
    public CompletableFuture<String> prepare(String emailId) {
        return CompletableFuture.completedFuture(
                "prepared:" + emailId);
    }
}
```

Đây là **fragment dự án Spring**: method mẫu chỉ nối chuỗi nên trong thực tế không cần async. Nó minh họa cách chọn executor theo **bean name**: `@Async("ioExecutor")`. Đảm bảo không có nhiều bean trùng tên trong context và caller không gọi method trực tiếp từ bên trong chính `EmailService`.

### 7.1. Số luồng và queue không được để mặc định một cách vô thức

Với `ThreadPoolTaskExecutor` sử dụng underlying `ThreadPoolExecutor`:

1. Pool có thể tạo worker cho task mới khi đang dưới `corePoolSize`.
2. Khi đã đủ core worker, task thường được đưa vào queue nếu queue còn chỗ.
3. Khi queue không nhận thêm và số worker chưa đến `maxPoolSize`, pool có thể mở rộng.
4. Khi không còn chỗ nhận task, chính sách rejection được áp dụng.

Vì vậy tăng `maxPoolSize` nhưng giữ queue vô hạn **không** nhất thiết làm pool dùng thêm worker. Việc `@EnableAsync` đã có không giải quyết queue pressure; phải chọn executor policy theo tải.

Khi dùng `AbortPolicy`, caller có thể nhận exception tại thời điểm submit task nếu pool không nhận. Đây là khác biệt quan trọng giữa **lỗi submit** và **lỗi nghiệp vụ bên trong task** (thường quan sát qua future). Hệ thống phải xử lý cả hai.

### 7.2. Nếu không tự khai báo executor thì sao?

Với Spring Framework, async support có cơ chế tìm executor thích hợp, ví dụ dựa trên một `TaskExecutor` phù hợp hoặc một `Executor` tên quy ước `taskExecutor`; nếu không tìm thấy, có fallback kiểu `SimpleAsyncTaskExecutor` theo phiên bản/framework setup.

Fallback này không đồng nghĩa với một bounded thread pool production-ready. Không dựa vào nó cho khối lượng lớn mà không hiểu giới hạn concurrency và tài nguyên.

Spring Boot có thể auto-configure bean executor, nhưng điều kiện, tên và kiểu bean phụ thuộc phiên bản, custom executor đang có, virtual-thread mode và integration được dùng. Khi cần xác định chắc chắn method dùng pool nào, `@Async("ioExecutor")` là cách ít mơ hồ.

## 8. Chọn mặc định bằng AsyncConfigurer

Trong cùng một ApplicationContext, nếu nhiều method dùng `@Async` **không có qualifier**, `AsyncConfigurer.getAsyncExecutor()` có thể trả về một `Executor` mặc định được chọn có chủ đích. Đây là một điểm cấu hình của hạ tầng đã được bật bằng `@EnableAsync`, không thay thế cho annotation bật async và không ép các lời gọi `@Async("ioExecutor")` dùng cùng pool.

`AsyncConfigurer` còn cho phép đăng ký `AsyncUncaughtExceptionHandler` để quan sát lỗi từ method `@Async void`. Nếu muốn sử dụng `ThreadPoolTaskExecutor`, nên quản lý nó như Spring bean và xác minh vòng đời initialize/shutdown; class implementing `AsyncConfigurer` có thể được khởi tạo sớm nên tránh injection vòng hay dependency chưa sẵn sàng.

Trong bước **bật cơ chế** của bài này, chỉ cần biết chỗ cấu hình executor mặc định nằm ở đâu và không làm thay đổi tác dụng của `@EnableAsync`. Khi thiết kế nhiều executor, phải kiểm thử pool nào thực thi từng method; cấu hình core/max/queue phụ thuộc tải và giới hạn downstream.

## 9. Hợp đồng kiểu trả về và lỗi cần kiểm tra ngay khi bật async

Khi qua Spring async proxy, method hỗ trợ `void`, `Future<T>` hoặc `CompletableFuture<T>`. Method trả trực tiếp `String` hay `int` không phải hợp đồng trả giá trị được interceptor hỗ trợ. Ví dụ sau nằm trong một service bean có executor `ioExecutor`; đây là một fragment, không phải lớp chạy độc lập:

```java
@Async("ioExecutor")
public CompletableFuture<Integer> calculate(int value) {
    if (value < 0) throw new IllegalArgumentException("negative");
    return CompletableFuture.completedFuture(value * 2);
}
```

Caller nhận handle từ proxy để ghép hoặc chờ với timeout; lỗi bên trong worker của method trả Future sẽ được phản ánh qua exceptional completion. Với `void`, lỗi không có kênh Future và cần `AsyncUncaughtExceptionHandler`/log phù hợp. Rejection của executor tại lúc gửi việc lại có thể xảy ra ngay trên đường gọi, trước khi nhận handle.

Đặt `@EnableAsync` thành công không tự bảo đảm timeout, interruption, truyền transaction/context, retry hay durability. Hãy xác minh những hợp đồng đó riêng theo nhu cầu nghiệp vụ.

## 10. Các điều kiện không được bỏ qua khi khai báo @EnableAsync

### 10.1. Annotation phải được Spring nạp

Nếu đặt `@EnableAsync` lên một class không thuộc component scanning, chưa `@Import` hoặc chưa được đăng ký trực tiếp, Spring không thấy cấu hình đó. Việc file Java tồn tại trong source không chứng minh context đã bật async.

Có thể kiểm tra bằng cách lấy bean cấu hình trong context, quan sát condition/bean definitions và test method thực chạy trên executor. Trong Spring Boot, bật debug logs đúng cách giúp hiểu auto-config, nhưng còn phải xác minh annotation infrastructure của Framework.

### 10.2. Phương thức phải được gọi qua proxy

Khi chạy `AdviceMode.PROXY`, self-invocation không đi qua proxy. Xem trường hợp:

```java
@Service
class ExportService {
    public void start() {
        exportAsync(); // Lời gọi nội bộ: bypass proxy trong mode PROXY
    }

    @Async
    public void exportAsync() {
        // Code này không tự chuyển thread do start() gọi nội bộ.
    }
}
```

Đây là fragment (cần import annotations). Cách sửa thường tốt nhất: tách `exportAsync()` sang một bean khác và inject bean đó vào caller, hoặc thiết kế một entry point từ bên ngoài proxy. Không dựa vào `this.exportAsync()`.

### 10.3. Không gọi @Async trực tiếp từ @PostConstruct

`@PostConstruct` chạy trong giai đoạn lifecycle khởi tạo; không giả định async proxy đã sẵn sàng để xử lý chính một callback trên cùng bean. Không dùng `@Async` trên lifecycle callback rồi kỳ vọng nó chuyển thread. Nếu cần khởi động một tác vụ async, để một Spring-managed bean khởi tạo khác gọi qua proxy của service tại thời điểm phù hợp, hoặc dùng cơ chế application lifecycle/event đã được chọn đúng.

### 10.4. Không coi annotation là giải pháp thread-safety

`@EnableAsync` chỉ bật cách thực thi, không bảo vệ shared mutable state. Nếu service singleton chứa field mutable và hai task cùng sửa, vẫn có thể race condition. Tách immutable input/output, lock/atomic khi cần và hạn chế trạng thái request ở singleton.

### 10.5. Không mặc định thread context đi theo task

Spring transaction context, security context, `ThreadLocal`, MDC, request attributes và persistence context không mặc nhiên chuyển từ caller sang worker. Ví dụ, `@Transactional` của caller không có nghĩa mọi thao tác trong method `@Async` nằm trong cùng transaction của caller. Khi cần, mở transaction riêng ở worker, truyền immutable data/ID và cấu hình context propagation cho từng loại context được phép.

## 11. Bốn tình huống cấu hình hay gặp

| Tình huống | @EnableAsync | Executor | Kết luận |
| --- | --- | --- | --- |
| Bean có `@Async` nhưng context không bật xử lý async | Không | Có hoặc không | Annotation chưa chắc tạo async invocation |
| Context có `@EnableAsync`, service được gọi qua proxy | Có | Executor hợp lệ | Task được offload theo lựa chọn executor |
| Context có `@EnableAsync` nhưng method bị gọi qua `this` | Có | Có | Self-invocation có thể chạy đồng bộ |
| Boot auto-configure executor nhưng chưa bật annotation | Không | Có | Tồn tại executor không đồng nghĩa `@Async` đang có hiệu lực |
| `@EnableAsync` + `@Async("missingExecutor")` | Có | Không có bean được chỉ tên | Lời gọi async sẽ lỗi khi resolve executor |
| `@EnableAsync` + bean với pool/queue vô hạn | Có | Có | Vẫn có rủi ro tăng tải, bộ nhớ và độ trễ |
| `@EnableAsync` đặt ở parent context | Ở parent | Phụ thuộc context | Không suy ra hạ tầng của child context tự bật theo |
| `@EnableAsync(mode=ASPECTJ)` nhưng không có weaving thích hợp | Có trên giấy | Tùy | Không thể trông chờ advice hoạt động đúng chỉ từ annotation |

Trong từng trường hợp, hãy phân biệt **khai báo** và **đã quan sát được hành vi runtime**.

## 12. Debug: làm sao biết @EnableAsync có tác dụng?

Đây là một quy trình chẩn đoán nên thực hiện trước khi sửa thread pool:

1. **Xác định context:** lớp `@Configuration` có được scan/import không? `@EnableAsync` có nằm trong đúng context không?
2. **Xác định bean:** service được inject qua Spring hay bạn dùng `new`?
3. **Xác định call path:** caller gọi qua bean/proxy hay gọi `this.method()` trong cùng class?
4. **Xác định annotation:** method/class có `@Async`? Phương thức có phù hợp với loại proxy và kiểu trả về không?
5. **Xác định executor:** `@Async("...")` trỏ tới bean nào? Có `AsyncConfigurer` hoặc executor mặc định nào khác không?
6. **Kiểm tra thực thi:** ghi thread name của caller/worker; ưu tiên test với thread-name prefix của executor và future.
7. **Đo quá tải:** active count, pool size, queue depth, task rejected, timeout, queue wait; một method không chạy ngay có thể là do queue chứ không phải thiếu `@EnableAsync`.
8. **Kiểm tra Boot khi cần:** với Boot, xem auto-configuration conditions, profile, runtime bean type và property binding.
9. **Kiểm tra lỗi:** future có complete exceptionally không? Method `void` có handler/log thích hợp không?
10. **Kiểm tra shutdown:** task mới có bị reject vì context/executor đang đóng không?

Đặt log trong method async và in thread name là một bước tốt, nhưng không nên chỉ dựa vào việc “tên thread khác” để kết luận kiến trúc đã đúng. Đặc biệt nếu method dùng dữ liệu chung, phải test correctness lẫn lifecycle.

### 12.1. Kiểm tra proxy bằng Spring AOP

Trong code test hoặc diagnostic có Spring AOP tương ứng:

```java
Object bean = context.getBean(ReportService.class);
System.out.println(
        org.springframework.aop.support.AopUtils.isAopProxy(bean));
```

Đây là fragment, giả định `context` và `ReportService` tồn tại trong project. Giá trị `true` cho biết bean là AOP proxy, nhưng **không tự chứng minh** method đã được offload bởi đúng async advice. Hãy kết hợp với kiểm tra thread và executor. Một bean có thể có proxy cho nguyên nhân khác, ví dụ `@Transactional`.

### 12.2. Test không phụ thuộc Thread.sleep()

Nếu cần chứng minh task chạy trong worker và caller có thể tiếp tục, dùng `CountDownLatch` hoặc future với timeout, không dùng `Thread.sleep(100)` rồi đoán task sẽ hoặc chưa hoàn tất. Latch giúp điều phối thứ tự trong test, làm test ít phụ thuộc tốc độ máy.

Một test contract tốt cần xác nhận: lớp cấu hình đã được nạp; bean được lấy qua context; method `@Async("lessonExecutor")` thực sự ở worker; kết quả và exception observable; task không bị bỏ qua khi shutdown.

## 13. Bài thực hành: từ cấu hình tối thiểu đến kiểm chứng

### Bài 1 — Bật annotation

Tạo `AsyncConfig` với `@Configuration` và `@EnableAsync`. Khai báo một bean `WorkService` có method `@Async` trả `CompletableFuture<String>`. Gọi method từ một Spring-managed bean khác.

- In tên caller thread và worker thread.
- Giải thích vì sao phải gọi qua bean của Spring.
- Xóa `@EnableAsync` trong môi trường test cô lập và quan sát sự khác biệt.

### Bài 2 — Chỉ rõ executor

Thêm `@Bean("workExecutor") ThreadPoolTaskExecutor` với prefix `work-`, core=2, max=4, queue=10. Dùng `@Async("workExecutor")`. Test rằng thread xử lý có prefix đã đặt. Sau đó đổi tên qualifier sai có chủ đích và quan sát exception khi Spring không tìm thấy executor.

### Bài 3 — Tái hiện self-invocation

Trong cùng service, tạo `start()` gọi `this.runAsync()`, với `runAsync()` có `@Async`. Xác định thread thực thi. Sau đó tách `runAsync()` sang một bean khác, inject bean vào caller và kiểm chứng async trở lại. Giải thích bằng mô hình proxy.

### Bài 4 — Kiểu trả về và lỗi

Cho method `@Async` trả `CompletableFuture<Integer>` và cố ý ném một exception. Dùng `get()` hoặc completion handler để nhận lỗi; sau đó thử method `void` và cấu hình exception handler để ghi nhận lỗi đúng cách. Kiểm tra sự khác biệt giữa exception lúc submit bị reject và exception phát sinh trong task.

### Bài 5 — Spring Boot

Khai báo `@EnableAsync` trên `@SpringBootApplication` rồi chuyển sang một lớp `@Configuration` riêng; xác minh cả hai cách đều hiệu lực khi được load trong context. Thử thêm bean executor tùy chỉnh và kiểm tra property `spring.task.execution.*` có đang chỉnh đúng bean task sử dụng không. Không coi YAML là bằng chứng duy nhất.

### Bài 6 — Vòng đời

Đóng `ApplicationContext` trong lúc executor có task đang chạy. Kiểm tra cách task được xử lý/hủy theo cấu hình và deadline. Nêu rõ vì sao công việc buộc tồn tại qua JVM restart cần durable job/queue, chứ không chỉ `@EnableAsync`.

## 14. Checklist trước khi đưa vào production

- [ ] Có một `@Configuration` được Spring nạp với `@EnableAsync` trong đúng context.
- [ ] Mọi method async dự kiến được gọi thông qua Spring-managed bean và proxy.
- [ ] Đã rà soát self-invocation, private/final method, callback khởi tạo và kiểu trả về.
- [ ] Executor được lựa chọn có chủ đích: tên, kiểu, core/max/queue và rejection policy.
- [ ] Không mặc định Spring Boot tự bật `@Async` hoặc mọi custom executor nhận properties.
- [ ] Caller quan sát được lỗi: qua future/handler, log và metric theo nghiệp vụ.
- [ ] Có timeout, cancellation hợp tác và giới hạn tài nguyên cho các I/O/downstream.
- [ ] Không dựa vào transaction/ThreadLocal của caller tự động xuất hiện ở worker.
- [ ] Bean singleton không giữ per-request mutable state gây race giữa task.
- [ ] Executor do Spring quản lý có chính sách shutdown phù hợp; task bền vững có cơ chế ngoài JVM.
- [ ] Test kiểm chứng đúng thread, executor, exception và tình huống tải; không dựa vào `sleep`.
- [ ] Đã đối chiếu API và default theo Spring Framework / Spring Boot phiên bản thực tế.

**Kết luận:** Khai báo `@EnableAsync` trong lớp `@Configuration` là bước **bật hạ tầng xử lý annotation async**. Để `@Async` hoạt động đúng và an toàn, phải đồng thời bảo đảm cấu hình được nạp, lời gọi đi qua Spring proxy, executor có giới hạn phù hợp và vòng đời/lỗi/kết quả được quan sát. Thành công không chỉ là “method chạy ở thread khác”, mà là thực thi đúng tài nguyên với hành vi có thể kiểm chứng.

## 15. Tài liệu tham khảo chính thức

- Spring Framework — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableAsync`, `@Async`, executor qualification, exception handling và nguyên tắc proxy.
- Spring Framework Javadoc — [@EnableAsync](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): annotation attributes, scope context, `AsyncConfigurer` và chế độ advice.
- Spring Framework Javadoc — [@Async](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html): kiểu trả về và mục đích annotation.
- Spring Boot — [Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html): những thành phần executor do Boot tự cấu hình và các trường hợp tương tác với `@EnableAsync`.

Khi nâng cấp framework, hãy dùng đường dẫn tài liệu của **đúng phiên bản** trong project, vì auto-configuration và lựa chọn executor mặc định có thể khác giữa các release.
