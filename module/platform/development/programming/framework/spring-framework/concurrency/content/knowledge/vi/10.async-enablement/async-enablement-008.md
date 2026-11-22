# Chỉ định bộ thực thi theo tên hoặc qualifier trong @Async

## 1. Mục tiêu: một ứng dụng Spring, nhiều nhóm công việc

Trong Spring Framework, `@Async` cho phép một phương thức của bean Spring được gọi qua cơ chế xử lý bất đồng bộ. Thay vì thực thi ngay toàn bộ thân phương thức trong luồng gọi, Spring có thể gửi lời gọi vào một `Executor`/`TaskExecutor`. Khi ứng dụng chỉ có một nhóm công việc, cấu hình executor mặc định đôi khi là đủ. Nhưng trong hệ thống thực tế, nhiều nhóm tác vụ có đặc điểm rất khác nhau:

- **I/O-bound:** gọi API, đọc dữ liệu, gửi thông báo; thời gian chờ ngoài có thể lớn.
- **CPU-bound:** tính toán, chuyển đổi dữ liệu; nhiều worker hơn năng lực CPU chưa chắc có ích.
- **Tác vụ nhạy độ trễ:** cập nhật thông tin người dùng, phản hồi nhanh.
- **Tác vụ nền dài:** kết xuất báo cáo, xử lý tệp, công việc có thể chờ lâu hơn.

Nếu tất cả dùng chung một pool, các tác vụ dài có thể chiếm worker hoặc làm đầy queue, khiến tác vụ quan trọng phải đợi. Vì vậy cần **định tuyến từng phương thức `@Async` đến đúng executor**, bằng **tên bean** hoặc **qualifier**.

Ví dụ ý định thiết kế:

```text
                 Spring-managed service
                         |
             +-----------+-----------+
             |                       |
      @Async("ioExecutor")    @Async("computeLane")
             |                       |
             v                       v
       Executor A                Executor B
       io-worker-*               cpu-worker-*
       chờ I/O                   tính CPU
       queue riêng               queue riêng
```

**Cú pháp cần nắm:**

```java
@Async("ioExecutor")
public CompletableFuture<String> fetchData() {
    // Chạy bằng executor phù hợp với tên "ioExecutor".
    return CompletableFuture.completedFuture("done");
}
```

Đây là một **mảnh phương thức Spring**, không phải chương trình Java độc lập. Chuỗi `"ioExecutor"` nằm trong thuộc tính `value` của `@Async`. Spring dùng nó để tìm một bean executor phù hợp theo **bean name hoặc qualifier**, không phải để tạo pool mới và cũng không phải tên thread.

Kết quả mong đợi sau bài: bạn hiểu cách khai báo nhiều executor, chọn theo bean name/qualifier, ưu tiên annotation ở phương thức so với lớp, khai báo chọn executor bằng property, tránh các lỗi proxy/self-invocation, và kiểm thử việc định tuyến có thực sự hoạt động.

## 2. Điều kiện tiên quyết để @Async có hiệu lực

Chỉ viết `@Async("...")` trên một method **chưa đủ**. Trong mô hình dùng proxy của Spring, thường cần:

1. Có `@EnableAsync` trong một lớp `@Configuration` thuộc `ApplicationContext` phù hợp, hoặc cấu hình annotation-driven tương ứng.
2. Đối tượng chứa method phải là **bean được Spring quản lý**, không phải đối tượng do code nghiệp vụ tự `new` rồi gọi trực tiếp.
3. Lời gọi phải đi **qua Spring proxy**, ví dụ một bean khác inject service rồi gọi method.
4. Method phải có chữ ký hỗ trợ `@Async`: điển hình `void`, `Future<T>` hoặc `CompletableFuture<T>`; không khai báo return type bất kỳ như `String` rồi mong Spring tự chuyển đổi.
5. Executor được chỉ định phải là một bean `Executor`/`TaskExecutor` thực sự phù hợp và có thể được Spring tìm thấy.

Một lời gọi đúng theo hướng proxy:

```text
Bean A (caller)
  -> proxy của Bean B
      -> interceptor @Async
          -> tìm Executor theo value
              -> execute/submit nhiệm vụ
                  -> worker gọi thân phương thức Bean B
```

Nếu Bean B tự gọi `this.asyncMethod()` trong chính nó, lời gọi không đi qua proxy Spring ở chế độ mặc định và thân phương thức thường chạy đồng bộ trên caller. Khi đó, dù cú pháp `@Async("ioExecutor")` hoàn toàn đúng, **không có định tuyến sang executor** như mong đợi.

Tài liệu Spring ghi rõ `@EnableAsync` chỉ kích hoạt xử lý trong **application context cục bộ**. Với ứng dụng có nhiều context (ví dụ root context và servlet context tách nhau), phải đặt cấu hình đúng nơi các bean được quản lý.

## 3. @Async("name"): chọn executor theo bean name

Cách trực tiếp nhất là khai báo một executor bean có tên rõ ràng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ExecutorConfiguration {

    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("io-worker-");
        return executor;
    }
}
```

Đây là **class cấu hình Spring** cần dependency Spring Framework. Nó không có phương thức `main`. Khi Spring tạo bean, tên được đăng ký là `ioExecutor`. Một phương thức bất đồng bộ khác có thể dùng đúng tên đó:

```java
@Async("ioExecutor")
public CompletableFuture<String> callRemoteApi(String id) {
    // Mã minh họa; không thực hiện mạng thật.
    return CompletableFuture.completedFuture("fetched-" + id);
}
```

Điểm mấu chốt: **tên trong `@Async` phải khớp bean name hoặc qualifier được đăng ký**. Nếu đặt `@Bean("ioExecutor")` nhưng ghi `@Async("io-worker-")` thì Spring không suy ra executor từ thread name prefix. Thread prefix chỉ giúp quan sát worker trong log/thread dump.

`@Async("ioExecutor")` và `@Async(value = "ioExecutor")` mang cùng ý nghĩa: `value` là thuộc tính của annotation và có thể lược tên thuộc tính khi cung cấp một giá trị.

**Đừng nhầm tên bean với tên phương thức cấu hình.** Với:

```java
@Bean("ioExecutor")
public ThreadPoolTaskExecutor makeIoPool() { /* ... */ }
```

Tên bean được chỉ định là `ioExecutor`, dù method Java tên `makeIoPool`. Với `@Bean` không truyền tên, tên phương thức thường trở thành tên bean mặc định; nên ưu tiên tên tường minh khi dùng để định tuyến `@Async`.

## 4. @Async("qualifier"): chọn theo nhãn @Qualifier

Spring cho phép đánh dấu một executor bean bằng qualifier. `@Async` có thể dùng **giá trị qualifier** làm tên tra cứu, ngay cả khi bean thực sự mang tên khác.

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ComputePoolConfiguration {

    @Bean("computeExecutor")
    @Qualifier("computeLane")
    public ThreadPoolTaskExecutor computeExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("cpu-worker-");
        return executor;
    }
}
```

Phía service:

```java
@Async("computeLane")
public CompletableFuture<Integer> calculate(int input) {
    return CompletableFuture.completedFuture(input * 2);
}
```

Trong trường hợp này:

| Thành phần | Giá trị | Vai trò |
|---|---|---|
| `@Bean("computeExecutor")` | `computeExecutor` | Tên bean thực sự trong container |
| `@Qualifier("computeLane")` | `computeLane` | Nhãn qualifier gắn với định nghĩa bean executor |
| `@Async("computeLane")` | `computeLane` | Yêu cầu Spring chọn executor có qualifier này |
| `setThreadNamePrefix("cpu-worker-")` | `cpu-worker-` | Tiền tố đặt tên worker thread, **không** được dùng để chọn bean |

**Qualifier không phải một executor khác.** Dùng qualifier chỉ thay cách xác định bean, còn tài nguyên thread/queue vẫn thuộc về đối tượng executor đã đăng ký. Điều này hữu ích khi muốn giữ tên bean ổn định cho wiring cũ, nhưng gắn nhãn theo ý nghĩa nghiệp vụ cho các phương thức `@Async`.

Một qualifier có thể là cách ghi lại vai trò logic, ví dụ `computeLane`, `reporting`, `notifications`, thay vì buộc phương thức nghiệp vụ biết tên triển khai cụ thể. Tuy nhiên, đừng cố tình gán một qualifier chung cho nhiều executor tương đương rồi dùng giá trị đó trong `@Async`: nếu không chọn được một bean duy nhất, việc phân giải có thể thất bại vì nhập nhằng.

### 4.1. @Qualifier ở vị trí nào mới liên quan?

`@Qualifier` dùng để chọn bean ở **điểm inject**:

```java
public MyService(@Qualifier("computeExecutor") Executor executor) {
    this.executor = executor;
}
```

không có nghĩa mọi method `@Async` trong `MyService` sẽ tự dùng executor đó. `@Async` có cơ chế chọn executor **riêng** thông qua `value`, executor mặc định hoặc `AsyncConfigurer`.

Muốn chọn qua qualifier trong annotation, phải gắn qualifier **lên định nghĩa executor bean** và viết `@Async("computeLane")` ở phương thức cần chạy, như ví dụ trên. Đừng đặt `@Qualifier` lên một tham số không liên quan rồi cho rằng nó sẽ thay thế nội dung `@Async`.

## 5. Ví dụ đầy đủ chạy được bằng Java 17 + Spring Framework

Ví dụ này cố ý dùng **hai executor tách biệt**. Một method chọn theo **tên bean**, method khác chọn theo **qualifier**, sau đó in tên thread thực sự đang chạy để chứng minh định tuyến.

Đây là dự án Maven tối giản, chạy trên **JDK 17+** với **Spring Framework 6.2.7**. Lấy đúng dependency/version trong `pom.xml` của ví dụ; khi dùng ứng dụng thật, chọn phiên bản phù hợp với BOM/stack của dự án.

### 5.1. Cấu trúc thư mục

```text
async-routing-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── lesson/
                └── AsyncRoutingDemo.java
```

### 5.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>lesson</groupId>
    <artifactId>async-routing-demo</artifactId>
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

`spring-context` cung cấp những thành phần Spring sử dụng trong bài; Maven sẽ tải các dependency liên quan theo metadata. Ví dụ sử dụng **proxy mode mặc định của `@EnableAsync`**, không cần thêm cấu hình AspectJ weaving.

### 5.3. Tệp src/main/java/lesson/AsyncRoutingDemo.java

```java
package lesson;

import java.util.concurrent.CompletableFuture;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncRoutingDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(Config.class)) {

            // Luôn lấy service từ Spring để lời gọi đi qua proxy.
            WorkService service = context.getBean(WorkService.class);

            String ioThread = service.readFromIo().join();
            String cpuThread = service.calculate().join();

            System.out.println("I/O executor: " + ioThread);
            System.out.println("CPU executor: " + cpuThread);
        }
    }

    @Configuration
    @EnableAsync
    public static class Config {

        @Bean("ioExecutor")
        public ThreadPoolTaskExecutor ioExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("io-worker-");
            return executor;
        }

        @Bean("cpuExecutor")
        @Qualifier("computeLane")
        public ThreadPoolTaskExecutor cpuExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("cpu-worker-");
            return executor;
        }

        @Bean
        public WorkService workService() {
            return new WorkService();
        }
    }

    public static class WorkService {

        // Chọn executor qua tên bean.
        @Async("ioExecutor")
        public CompletableFuture<String> readFromIo() {
            String thread = Thread.currentThread().getName();
            return CompletableFuture.completedFuture(thread);
        }

        // Chọn executor qua qualifier, không phải bean name.
        @Async("computeLane")
        public CompletableFuture<String> calculate() {
            String thread = Thread.currentThread().getName();
            return CompletableFuture.completedFuture(thread);
        }
    }
}
```

### 5.4. Chạy và đọc kết quả

Trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=lesson.AsyncRoutingDemo
```

Hai dòng do chương trình in ra trong lần chạy thành công:

```text
I/O executor: io-worker-1
CPU executor: cpu-worker-1
```

Maven có thể in thêm thông tin riêng của công cụ nếu thay đổi tùy chọn chạy. Phần **hai dòng trên** là nội dung từ `System.out.println` trong chương trình.

Tại sao có thể dự đoán tên thread ở ví dụ tối giản này?

- Hai pool được tạo độc lập, mỗi pool chỉ thực thi **một task** trong toàn bộ lần chạy.
- Spring sử dụng prefix tương ứng khi khởi tạo worker đầu tiên của mỗi pool, nên các tên là `io-worker-1` và `cpu-worker-1`.
- Chương trình lấy service từ `ApplicationContext`, nên lời gọi đi qua proxy có `@Async`.
- `join()` chạy ở luồng main để chờ từng kết quả **chỉ nhằm kiểm tra ví dụ**; thân method được worker của executor tương ứng thực thi.
- Các method trả `CompletableFuture.completedFuture(...)` bên trong worker vì phương thức đích phải giữ đúng kiểu trả về. Spring proxy trả một `CompletableFuture` đại diện cho phần chạy bất đồng bộ.

**Không sao chép cách gọi `join()` ngay trong mọi request HTTP** rồi cho rằng endpoint vẫn bất đồng bộ hoàn toàn: luồng request sẽ phải đợi. Trong ứng dụng thật, caller có thể trả về future, gắn callback, hoặc phối hợp kết quả không chặn theo contract của tầng trên.

Ví dụ này không làm HTTP thật hay tính toán nặng. Nó **kiểm chứng đường định tuyến** giữa method và executor, không phải bài benchmark I/O/CPU.

## 6. Có gì khác nhau giữa tên bean, qualifier và tên thread?

Ba khái niệm này khác hẳn nhau:

| Thuộc tính | Ai sử dụng? | Ví dụ | Nếu đổi thì sao? |
|---|---|---|---|
| Bean name | Spring IoC/lookup | `ioExecutor` | Các lời gọi `@Async("ioExecutor")` có thể không còn tìm đúng bean |
| Qualifier | Spring IoC chọn một bean theo nhãn | `computeLane` | Các lời gọi chọn bằng qualifier phải đổi theo |
| Thread name prefix | Executor tạo worker thread | `cpu-worker-` | Chỉ ảnh hưởng tên worker, không đổi bean được chọn |
| Java method name khai báo bean | Java/Spring tạo bean | `cpuExecutor()` | Nếu `@Bean` có tên tường minh, đổi method name không nhất thiết đổi bean name |
| Tên method `@Async` | Nghiệp vụ / proxy method | `calculate()` | Không tự quyết định tên executor |

Không dùng tên thread để tìm executor: log có dòng `cpu-worker-1` không có nghĩa bean tên `cpu-worker-1`. Ngược lại, một executor bean tên `reportingExecutor` có thể đặt tiền tố thread là `report-` mà vẫn được chọn bằng `@Async("reportingExecutor")`.

Khi đặt tên, hãy ưu tiên mô tả **nhóm tải** hoặc **ý nghĩa tài nguyên**: `ioExecutor`, `reportExecutor`, `mailExecutor`, `computeLane`. Tránh biến tên bean thành thông số triển khai như `poolWithEightThreads`, vì sau khi thay cấu hình kích thước thì tên sẽ gây hiểu lầm.

## 7. @Async ở cấp lớp và ưu tiên ở cấp phương thức

`@Async` cho phép khai báo trên **class** lẫn **method**. Nếu gắn ở class, các phương thức phù hợp trong class trở thành ứng viên xử lý bất đồng bộ. Method có `@Async` với `value` cụ thể sẽ **ưu tiên hơn executor được chỉ định ở class**.

Ví dụ:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
@Async("ioExecutor")
public class MixedWorkService {

    public CompletableFuture<String> fetch() {
        return CompletableFuture.completedFuture("I/O");
    }

    @Async("computeLane")
    public CompletableFuture<String> transform() {
        return CompletableFuture.completedFuture("CPU");
    }
}
```

Đây là **Spring component**, không có chương trình `main` độc lập; giả định các executor `ioExecutor` và qualifier `computeLane` đã tồn tại.

| Method | Chọn executor | Vì sao |
|---|---|---|
| `fetch()` | `ioExecutor` | Dùng cấu hình `@Async("ioExecutor")` tại class |
| `transform()` | `computeLane` | `@Async("computeLane")` tại method ghi đè lựa chọn của class |

**Đừng hiểu class-level annotation là cách đổi default executor toàn ứng dụng**: nó chỉ áp dụng cho phạm vi class được đánh dấu. Nếu muốn đặt mặc định chung cho các phương thức dùng `@Async` không có `value`, cấu hình executor mặc định ở `@EnableAsync`/`AsyncConfigurer` hoặc cấu hình tương đương.

Dùng class-level khi đa số method trong service thực sự cùng một nhóm tải. Nếu chỉ có một hoặc hai method cần bất đồng bộ, gắn method-level thường dễ kiểm soát hơn: tránh vô tình biến method khác thành async, đặc biệt sau khi thêm method mới.

Lưu ý JavaDoc của `@Async`: không áp dụng annotation này cho các method khai báo trong một class `@Configuration`. Hãy đặt business method vào service/component riêng và để configuration chỉ khai báo tài nguyên.

## 8. Khi annotation không có value, điều gì thay đổi?

`@Async` không qualifier dùng executor mặc định của context: có thể do `AsyncConfigurer` trả về, do Spring Framework tra một `TaskExecutor` có thể chọn, rồi bean `Executor` tên `taskExecutor`, hoặc fallback khi không có ứng viên. Spring Boot còn có thể cung cấp sẵn executor qua auto-configuration. Vì thế có hai đường khác nhau:

```java
@Async                    // Mặc định, phụ thuộc cấu hình context.
public CompletableFuture<String> generalJob() {
    return CompletableFuture.completedFuture("general");
}

@Async("ioExecutor")       // Chỉ định bean/qualifier cụ thể.
public CompletableFuture<String> ioJob() {
    return CompletableFuture.completedFuture("io");
}
```

Đây là các method minh họa trong Spring service, không phải file Java độc lập. Khi cần kiểm soát SLA theo nhóm công việc, phương thức có yêu cầu riêng nên chọn qualifier rõ ràng và được test trong context thực; `@Primary` hay một tên bean bất kỳ không thay thế bằng chứng đường định tuyến.

## 9. Chọn tên executor thông qua property placeholder hoặc SpEL

JavaDoc `Async.value` cho phép cung cấp một **property placeholder** hoặc **SpEL expression** thay vì hard-code tên bean. Đây là cách hữu ích để chuyển tuyến theo môi trường triển khai mà không phải sửa annotation.

### 9.1. Property placeholder

Giả sử cấu hình Environment chứa:

```properties
app.async.report-executor=ioExecutor
```

Service có thể viết:

```java
@Async("${app.async.report-executor}")
public CompletableFuture<String> createReport(String id) {
    return CompletableFuture.completedFuture(id);
}
```

Trong văn bản code ở trên, chuỗi bắt đầu bằng **dấu dollar và dấu ngoặc nhọn** theo cú pháp Spring property placeholder. Khi Spring resolve thành `ioExecutor`, executor bean có tên ấy được chọn. Đây là **mảnh method Spring** cần đúng property source, context và bean executor.

Trong Spring Boot, property có thể được khai báo trong `application.properties`, biến môi trường hoặc cơ chế cấu hình tương thích; khi dùng Spring Framework thuần, cần khai báo property source/Environment phù hợp. Nếu property không được giải quyết hoặc giá trị chỉ tới bean không tồn tại, việc định tuyến có thể thất bại, không nên lặng lẽ thay bằng executor khác.

### 9.2. SpEL

Có thể lấy tên qua Spring Expression Language:

```java
@Async("#{environment['app.async.report-executor']}")
public CompletableFuture<String> createReport(String id) {
    return CompletableFuture.completedFuture(id);
}
```

Giá trị property trong ví dụ vẫn là `ioExecutor`. JavaDoc mô tả giá trị `@Async.value` được resolve động khi là SpEL hoặc placeholder; điều này không đồng nghĩa nó là một expression tùy ý có thể phụ thuộc trực tiếp vào mọi tham số method mà không có thiết kế context phù hợp.

**Chọn cách nào?**

- Tên cố định `@Async("ioExecutor")`: dễ đọc và dễ phát hiện sai cấu hình.
- Placeholder `@Async("${app.async.report-executor}")`: phù hợp khi cần chọn tên theo môi trường hoặc cấu hình deploy.
- SpEL: phù hợp khi cần logic resolution rõ ràng hơn, nhưng nên giữ biểu thức đơn giản, dễ test.

Với nhu cầu chuyển executor **theo từng request/tenant** ở runtime, đừng mặc định placeholder/SpEL sẽ làm một bộ điều phối công việc động hoàn chỉnh. Hãy xác định chính sách định tuyến trong service hoặc một abstraction riêng, tránh biến annotation thành nơi chứa logic khó kiểm soát.

## 10. Phân biệt qualifier cho injection và qualifier cho @Async

Xét service sau:

```java
import java.util.concurrent.Executor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Async;

public class ConfusingService {
    private final Executor executor;

    public ConfusingService(
            @Qualifier("ioExecutor") Executor executor) {
        this.executor = executor;
    }

    @Async("computeLane")
    public void process() {
        System.out.println("Đang xử lý");
    }
}
```

Đây là class minh họa, cần đăng ký làm bean Spring để `@Async` có hiệu lực.

Ý nghĩa chính xác:

- `@Qualifier("ioExecutor")` ở constructor lựa chọn bean để gán vào **field executor**.
- `@Async("computeLane")` trên `process()` lại yêu cầu **computeLane** thực thi thân method.
- Field `executor` không hề được gọi trong `process()`; qualifier trên constructor **không** ép `@Async` phải dùng `ioExecutor`.

Đây là hai cơ chế tách biệt, dù cùng dùng từ “qualifier”. Nếu service vừa gửi thủ công qua field vừa dùng `@Async`, rất dễ có hai đường thực thi khác nhau. Hãy đặt tên nhất quán, tài liệu hóa nhiệm vụ của từng pool và viết test phân biệt chúng.

### 10.1. Có thể dùng Executor thay vì TaskExecutor?

Có. JavaDoc `Async.value` đề cập matching với bean kiểu `java.util.concurrent.Executor` **hoặc** `org.springframework.core.task.TaskExecutor`. Vì `TaskExecutor` mở rộng `Executor`, một Spring `ThreadPoolTaskExecutor` đáp ứng cả hai.

Bạn cũng có thể đăng ký `Executor` do thư viện khác cung cấp rồi cho Spring sử dụng, nhưng phải xác định ai sở hữu pool, vòng đời và chính sách từ chối. Không nên biến một tài nguyên chỉ dùng chung làm pool bị shutdown bởi service con.

Trong Jakarta EE, `DefaultManagedTaskExecutor` có thể được đăng ký như Spring bean để chuyển tới managed executor qua JNDI. `@Async("managedExecutor")` chọn bean Spring có tên đó; việc quản lý worker do Jakarta EE server thực hiện. Đây là một lựa chọn executor khác, không thay đổi ý nghĩa của tham số `value`.

## 11. Chọn đúng tên executor nhưng method vẫn không được định tuyến?

Trong `AdviceMode.PROXY` mặc định, việc phân giải bean name/qualifier chỉ diễn ra khi lời gọi đi **qua Spring-managed proxy**. Nếu cùng bean gọi `this.runInBackground()`, hoặc object được tạo thủ công bằng `new`, async interceptor không tham gia. Method `private`/`final` và code trong constructor/lifecycle cũng không phải điểm chặn thích hợp của proxy thông thường; `@Async` không được hỗ trợ trên method khai báo trong `@Configuration`.

Để tách hai nhóm lỗi, trước tiên xác minh context có `@EnableAsync`, bean do Spring quản lý và method public/non-final được gọi từ bean khác. Sau đó kiểm tra bean `Executor` theo tên hoặc qualifier `@Async("...")`. Nếu đã qua proxy nhưng tên sai hoặc qualifier nhập nhằng, lời gọi có thể thất bại lúc chọn executor; nếu pool đầy, submission có thể bị từ chối. Đổi `proxyTargetClass` không sửa tên bean sai hay làm private/final method trở thành điểm chặn hợp lệ.

Khi rename `@Bean("ioExecutor")` hoặc `@Qualifier("computeLane")`, tìm tất cả các method `@Async` đang tham chiếu và chạy lại integration test với cả hai pool. Dùng thread-prefix để quan sát, nhưng không dùng tên thread làm dữ liệu nghiệp vụ.

## 12. Kết quả và ngoại lệ khi đã định tuyến đúng

Chọn đúng executor chỉ giải quyết **nơi công việc được chạy**. Caller và service vẫn phải quản lý kết quả, lỗi, thời hạn và trạng thái nghiệp vụ.

### 12.1. Method trả void

```java
@Async("ioExecutor")
public void sendNotification(String id) {
    // Làm việc trên executor đã chọn; không có kết quả cho caller.
}
```

Nếu thân method ném ngoại lệ trên worker, caller không có `Future` để bắt trực tiếp. Spring cung cấp `AsyncUncaughtExceptionHandler` cho những ngoại lệ từ method `@Async` có kiểu trả về `void`; hành vi mặc định là ghi log. Các lỗi xảy ra **trước khi task được nhận** (ví dụ executor bị từ chối) là tình huống khác cần xử lý ở biên gửi việc.

### 12.2. Method trả CompletableFuture

```java
@Async("computeLane")
public CompletableFuture<Integer> twice(int x) {
    if (x < 0) {
        throw new IllegalArgumentException("x phải không âm");
    }
    return CompletableFuture.completedFuture(x * 2);
}
```

Khi gọi **qua Spring proxy**, caller nhận một `CompletableFuture<Integer>` đại diện cho phần thực thi async. Nếu phần code trên worker ném `IllegalArgumentException`, future của caller hoàn tất theo hướng lỗi; caller có thể gắn `exceptionally(...)`, `handle(...)` hoặc quan sát exception khi `join()/get()`.

Ví dụ:

```java
CompletableFuture<Integer> future = service.twice(-1);
future.whenComplete((value, error) -> {
    if (error != null) {
        System.err.println("Tác vụ thất bại: " + error);
    }
});
```

Đây là **mảnh mã caller** có biến `service` được inject/tra cứu từ Spring; không phải chương trình chạy độc lập. Nếu dùng `join()` hoặc `get()` thì caller có thể bị chặn; điều này cần cân nhắc nếu đang ở HTTP request thread.

### 12.3. Lỗi khi executor quá tải

`ThreadPoolTaskExecutor` có thể từ chối tác vụ mới khi worker/queue đầy hoặc pool đóng. Với cấu hình `AbortPolicy` thông thường, Spring thể hiện rejection bằng `TaskRejectedException` từ đường gửi. Điều đó không có nghĩa method nghiệp vụ đã được chạy rồi thất bại.

Hai loại lỗi khác nhau:

| Thời điểm | Ví dụ | Nơi xử lý |
|---|---|---|
| Phân giải/chọn executor | `@Async("missingPool")`, tên sai hoặc qualifier nhập nhằng | Sửa cấu hình, bean name và test wiring |
| Gửi task | Pool đã shutdown hoặc quá tải | Caller hoặc biên nhận request: backpressure, lỗi/retry phù hợp |
| Task đang chạy | Exception của logic bên trong `@Async` | `Future/CompletableFuture` hoặc `AsyncUncaughtExceptionHandler` với `void` |
| Task hoàn thành quá muộn | Deadline request đã hết hoặc kết quả hết giá trị | Timeout, cancel, kiểm tra deadline và idempotency |

Không được nuốt exception từ chối rồi vẫn trả “đã xử lý” cho người dùng. `@Async` không phải message broker bền vững: nếu JVM crash, các công việc chỉ còn trong queue bộ nhớ có thể mất.

## 13. Đặt pool theo đặc điểm tải, không chỉ theo tên

Định tuyến có ích khi pool được thiết kế theo hành vi công việc.

| Nhóm | Ví dụ | Điều cần cân nhắc |
|---|---|---|
| I/O-bound | HTTP, database, RPC | Giới hạn connection, timeout, downstream capacity, số worker |
| CPU-bound | Xử lý số liệu, nén, transform | Số lõi, CPU quota, contention, tránh over-subscription |
| Ít tốn thời gian nhưng quan trọng | Cập nhật trạng thái nhanh | Queue và độ trễ p95/p99; không bị job dài làm nghẽn |
| Công việc nền dài | Báo cáo, xử lý tệp | Hàng đợi giới hạn, khả năng retry, lưu job bền vững nếu cần |

Có hai pool riêng không có nghĩa chúng cách ly hoàn toàn. Chúng vẫn chia sẻ CPU, heap, GC, database, mạng và cả tài nguyên của các hệ thống ngoài. Nếu hai pool cùng tranh nhau một connection pool nhỏ, cô lập ở tầng executor chưa đảm bảo cô lập năng lực downstream.

Các cấu hình `corePoolSize`, `maxPoolSize`, `queueCapacity` cần được chọn cùng nhau. Với `ThreadPoolExecutor` bên dưới `ThreadPoolTaskExecutor`, khi đạt số worker lõi, hệ thống thường ưu tiên xếp hàng trước khi mở thêm worker tới max. Một queue quá lớn có thể khiến `maxPoolSize` gần như không được dùng; queue quá nhỏ có thể dẫn tới rejection khi burst.

**Cách đo và xác nhận:**

- Log/metrics phân tách theo **tên executor**: submitted, active, queued, completed, rejected.
- Kiểm tra `getPoolSize()`, `getActiveCount()` và queue size bằng API/monitoring được Spring hỗ trợ cho phiên bản đang chạy.
- Đo thời gian từ lúc task được gửi đến khi worker bắt đầu, p95/p99 latency và thời gian xử lý.
- Giám sát connection pool, CPU, heap, GC và upstream retries.
- Đặt giới hạn đồng thời hoặc rate limit nếu lượng gửi vượt năng lực xử lý; tăng queue không tạo thêm thông lượng.
- Chọn chính sách khi ứng dụng đóng: task mới bị từ chối, task đang chạy xử lý thế nào, task đang chờ có được hoàn tất hay hủy.

Không tạo một pool mới mỗi lần gọi `@Async` và không tự `shutdown()` một executor bean dùng chung từ một service đơn lẻ. Để Spring/container quản lý lifecycle của bean; trách nhiệm nghiệp vụ là gửi việc có kiểm soát và quan sát kết quả.

## 14. ThreadLocal, security context và transaction không tự theo executor

Một executor được chọn đúng theo `@Async("ioExecutor")` không đồng nghĩa mọi dữ liệu của luồng gọi tự có ở worker:

- `ThreadLocal` tự tạo và MDC logging thường gắn với thread đang gọi.
- `SecurityContextHolder` và ngữ cảnh request của Spring cần cơ chế truyền phù hợp nếu task thực sự cần chúng.
- Spring transaction thường gắn với thread; method `@Async` chạy trên worker **không tự tham gia transaction của caller**.
- Một `EntityManager`, JDBC connection hoặc request object có vòng đời riêng; không nên chuyển các đối tượng đó sang worker để sử dụng tùy tiện.

Nếu task cần `correlationId`, `tenantId` hay thông tin nhận diện phục vụ xử lý, truyền **dữ liệu bất biến cần thiết** qua tham số hoặc dùng cơ chế context propagation đã được kiểm chứng. Nếu task cần transaction, thiết kế transaction mới trên đường thực thi thích hợp.

Quan trọng: chọn executor là một **quyết định định tuyến tác vụ**, không thay thế đảm bảo về transaction, security, context propagation hay sự tồn tại bền vững của công việc.

## 15. Kiểm chứng chọn đúng executor trong kiểm thử

Tối thiểu nên có một bài integration test chạy với `ApplicationContext` thật:

1. Khởi tạo context có `@EnableAsync` và cả hai executor.
2. Lấy service từ Spring, không `new` trực tiếp.
3. Gọi method `@Async("ioExecutor")` và method `@Async("computeLane")`.
4. Quan sát thread name/pool metrics hoặc thực thi task đánh dấu rõ mốc bắt đầu; xác định mỗi method đi vào pool mong muốn.
5. Dùng `CompletableFuture`/`CountDownLatch` để chờ có thời hạn khi kiểm thử async; không dùng `Thread.sleep(...)` rồi giả định task đã xong.
6. Thử đổi qualifier sai trong môi trường kiểm thử để hiểu lỗi lookup; khôi phục đúng tên.
7. Thử self-invocation để biết vì sao annotation có thể không có hiệu lực.
8. Thử quá tải có kiểm soát và xác nhận rejection được báo đúng.

### 15.1. Vì sao không chỉ kiểm tra @Bean tồn tại?

`context.containsBean("ioExecutor")` chỉ chứng minh có bean tên đó. Nó **không chứng minh** method `@Async` đã được proxy hoặc thực sự dùng bean ấy. Có thể có bean đúng nhưng lời gọi đi qua `this` làm mất interception.

Ngược lại, nhìn thấy hai tên thread khác nhau cũng chưa đủ trong một hệ thống lớn: thread có thể được tạo bởi pool khác trùng prefix. Ví dụ `AsyncRoutingDemo` đặt hai prefix phân biệt và chạy riêng nên đủ để học nguyên tắc; trong production nên kết hợp quan sát bean wiring, pool metrics và test cụ thể.

### 15.2. Không biến thread name thành hợp đồng nghiệp vụ

Tên thread phù hợp để debug hoặc test mẫu, nhưng **không phải API bảo đảm kết quả nghiệp vụ**. Người dùng không cần biết task chạy trên `io-worker-1` hay `io-worker-3`; họ cần biết công việc đã được tiếp nhận, có thể theo dõi, và lỗi được xử lý.

Nếu test production phụ thuộc số thứ tự thread cụ thể, nó dễ lỗi khi tăng pool size hoặc thay thread factory. Test nên chứng minh tác vụ đi vào **đúng executor logic**, không đóng đinh một thread ID không liên quan.

## 16. Sử dụng qualifier từ XML và trường hợp hỗn hợp

Dự án Spring cũ có thể cấu hình executor và qualifier bằng XML. Nguyên tắc vẫn giống Java Configuration: `@Async.value` có thể tìm theo tên bean hoặc qualifier gắn với executor.

Đoạn XML **minh họa**, nằm trong tệp Spring XML đã khai báo namespace `beans`/`task` hợp lệ:

```xml
<bean id="computeExecutor"
      class="org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor">
    <qualifier value="computeLane"/>
    <property name="corePoolSize" value="2"/>
    <property name="maxPoolSize" value="2"/>
    <property name="queueCapacity" value="8"/>
</bean>
```

Sau đó `@Async("computeLane")` vẫn có thể dùng nhãn đó để lựa chọn. Nếu XML cấu hình annotation-driven executor mặc định, đó là cấu hình default; nó không thay thế được lựa chọn cụ thể của mọi method có `@Async("...")`.

Khi một ứng dụng trộn Java Configuration, XML, Spring Boot auto-configuration và cấu hình có điều kiện theo profile, việc trùng tên bean hoặc trùng qualifier dễ xảy ra. Hãy liệt kê **những bean `Executor` thực sự tồn tại tại runtime**, theo đúng active profiles, thay vì suy luận chỉ từ file cấu hình nào đó.

## 17. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra và sửa |
|---|---|---|
| `@Async("ioExecutor")` nhưng method chạy trên thread request | Self-invocation, đối tượng tự `new`, chưa bật `@EnableAsync` | Gọi qua bean proxy; kiểm tra ApplicationContext |
| Không tìm thấy `ioExecutor` | Sai tên hoặc bean không được đăng ký vì profile/condition | Kiểm tra tên bean thực tế, namespace/context |
| `@Async("cpu-worker-")` không tìm được pool | Dùng thread prefix thay cho tên/qualifier | Dùng `@Bean("computeExecutor")` hoặc `@Qualifier("computeLane")` |
| `@Async("computeLane")` không chọn được bean | Qualifier chưa gắn lên executor bean, hoặc nhập nhằng | Khai báo qualifier đúng trên bean và bảo đảm chọn duy nhất |
| Constructor inject `@Qualifier("ioExecutor")` nhưng @Async dùng pool khác | Nhầm qualifier injection với `@Async.value` | Chỉ rõ executor ngay trên method |
| Đặt `@Async` ở class nhưng một method quan trọng vào sai pool | Không khai báo override ở method | Dùng `@Async("otherExecutor")` cho method cần khác |
| Ghi `@Async` không có value nhưng dự đoán theo một bean bất kỳ | Default selection khác mong đợi | Cấu hình AsyncConfigurer hoặc dùng tên tường minh |
| Đổi property chứa tên pool nhưng task không chạy | Placeholder không resolve, tên đích sai | Kiểm tra Environment và bean name/qualifier |
| Method annotated có return type `String` | Không phải kiểu trả về hợp lệ cho xử lý async thông thường | Dùng `void`, `Future` hoặc `CompletableFuture` |
| Exception từ method `void` không tới caller | Không có kết quả trả về | Cấu hình `AsyncUncaughtExceptionHandler` hoặc đổi API |
| Future bị lỗi nhưng không ai quan sát | Không có xử lý hoàn tất | Dùng `whenComplete`, `handle` hoặc cơ chế giám sát |
| Task bị từ chối khi queue đầy | Pool quá tải hoặc đã đóng | Thiết kế backpressure, xử lý `TaskRejectedException` |
| Context/security/transaction không còn | Thread mới không mặc định mang mọi context | Truyền thông tin đúng cách và tạo transaction phù hợp |
| Annotation trên method cấu hình `@Bean` | `@Async` không hỗ trợ trên method trong `@Configuration` | Đưa công việc sang service được Spring quản lý |

## 18. Bài tập thực hành

### Bài 1 — Chọn bằng tên bean

Khai báo hai `ThreadPoolTaskExecutor` có bean name `imageExecutor` và `mailExecutor`. Viết hai method tương ứng `resizeImage(...)` và `sendMail(...)` dùng `@Async` để mỗi method vào pool riêng.

**Định hướng:** Đặt `@Bean("imageExecutor")`/`@Bean("mailExecutor")` rồi dùng `@Async("imageExecutor")` và `@Async("mailExecutor")`. Hãy kiểm tra `@EnableAsync` và lời gọi qua proxy.

### Bài 2 — Chọn bằng qualifier

Bean có tên `batchPool` nhưng qualifier là `reports`. Viết method `generateReport()` định tuyến theo qualifier mà không đổi tên bean.

**Định hướng:** Khai báo `@Bean("batchPool")`, `@Qualifier("reports")` trên định nghĩa bean, và `@Async("reports")` tại method. Qualifier dùng ở constructor injection của một thành phần khác không tự gán lại qualifier cho bean.

### Bài 3 — Ưu tiên class/method

Class `@Async("ioExecutor")` có hai method `fetch()` và `compute()`; riêng `compute()` khai báo `@Async("computeLane")`. Khi gọi qua proxy, method nào dùng pool nào?

**Định hướng:** `fetch()` dùng executor chỉ định ở class, `compute()` dùng executor chỉ định ở method.

### Bài 4 — Thay tên qua cấu hình

Thiết lập `app.async.report-executor=ioExecutor` và method `@Async("${app.async.report-executor}")`. Khi thay property thành `computeExecutor`, cần xác minh điều gì?

**Định hướng:** Phải có bean executor tên `computeExecutor`, property được resolve đúng trong context, và workload phải phù hợp pool mới. Đổi value không tự thay kích thước pool hoặc bảo đảm cách ly tài nguyên.

### Bài 5 — Tìm lỗi self-invocation

Một method đồng bộ `start()` của bean gọi `this.doAsync()`, dù `doAsync()` có `@Async("ioExecutor")`. Vì sao quan sát thấy nó vẫn chạy trên thread caller?

**Định hướng:** Lời gọi không đi qua proxy. Tách method async sang bean khác rồi inject/gọi qua Spring.

### Bài 6 — Chạy dự án Maven

Chạy `AsyncRoutingDemo` ở mục 5, xác minh hai dòng có prefix khác nhau. Sau đó đổi `@Async("computeLane")` thành `@Async("ioExecutor")` và dự đoán dòng thứ hai.

**Định hướng:** Hai lời gọi sẽ chọn cùng bean `ioExecutor`; ở cấu hình ví dụ với một worker đang được dùng tuần tự, prefix dòng thứ hai sẽ là `io-worker-`. Đây là thay đổi routing, không phải đổi tên method hay dữ liệu tính toán.

### Bài 7 — Chỉ định executor hay chỉnh pool?

Một team định tuyến đúng `@Async("reporting")` nhưng queue báo cáo tăng không ngừng. Cần tăng `maxPoolSize` hay tăng `queueCapacity` trước?

**Định hướng:** Không quyết định chỉ từ tên executor. Đo queue wait, throughput, thời gian chạy, giới hạn downstream và memory. Nếu queue dài, tăng queue thường làm chờ lâu hơn; nếu pool đã bị downstream chặn, tăng worker có thể gây thêm nghẽn. Xử lý giới hạn đầu vào và SLA trước khi chỉnh số.

## 19. Checklist áp dụng vào dự án

Khi một PR thêm hoặc sửa `@Async("...")`, hãy kiểm tra:

1. **Tên/qualifier:** Chuỗi trong annotation khớp chính xác bean name hoặc qualifier của một `Executor`/`TaskExecutor` hiện hữu.
2. **Đăng ký bean:** Bean executor có hiệu lực trong ApplicationContext và active profile cần dùng.
3. **Bật async:** `@EnableAsync`/cấu hình tương đương đã áp dụng trong đúng context.
4. **Đường gọi:** Method public, non-final (ở thiết kế proxy thông thường), được gọi qua proxy chứ không qua `this`.
5. **Ưu tiên:** Annotation method-level có chủ ý so với lựa chọn ở class-level/default.
6. **Kết quả:** Kiểu trả về `void/Future/CompletableFuture` phù hợp nhu cầu theo dõi; lỗi có kênh quan sát.
7. **Tài nguyên:** Worker/queue có giới hạn, phù hợp workload, có rejection policy.
8. **Ngữ cảnh:** Thông tin request/security/transaction cần dùng trong worker được xử lý đúng.
9. **Vòng đời:** Không tạo/shutdown pool trong mỗi request; hiểu hành vi dừng ứng dụng.
10. **Kiểm thử:** Có bằng chứng định tuyến qua Spring proxy và giám sát ở mức executor, không chỉ kiểm tra bean tồn tại.

## 20. Kết luận

- **`@Async("beanName")` chọn executor bean theo tên** đã đăng ký với Spring.
- **`@Async("qualifier")` cũng có thể chọn executor theo qualifier** như `@Qualifier("computeLane")` gắn lên định nghĩa bean.
- `@Async.value` không phải tên thread, không phải tên class tùy ý và không tự tạo pool mới.
- **Method-level selection ưu tiên class-level**, còn method không chỉ định executor dùng cấu hình mặc định phù hợp.
- `@EnableAsync` và **lời gọi đi qua Spring proxy** là điều kiện căn bản để việc định tuyến có hiệu lực ở chế độ proxy mặc định.
- Chọn đúng pool chưa đủ: phải quản lý **kết quả/lỗi, tài nguyên, context, transaction và quá tải** theo trách nhiệm của ứng dụng.
- Dùng **một bài kiểm thử tích hợp với hai executor** như ví dụ Maven để chứng minh method thực sự đi đến pool đã chọn.

### Tài liệu chính thức

- [Spring Framework Javadoc — Async](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework Javadoc — EnableAsync](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework Javadoc — AsyncConfigurer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework Javadoc — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
