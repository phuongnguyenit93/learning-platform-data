# Cơ chế tìm TaskExecutor hoặc bean taskExecutor khi không cấu hình tường minh

> **Module:** Spring Framework – concurrency  
> **Chủ đề cha:** Bật @Async  
> **Mục tiêu:** Giải thích chính xác Spring chọn `Executor` nào cho một phương thức `@Async` không ghi tên executor và ứng dụng không cung cấp `AsyncConfigurer.getAsyncExecutor()`; phân biệt tìm theo **kiểu bean**, tìm theo **tên bean**, executor dự phòng và cấu hình tự động của Spring Boot.

## 1. Câu trả lời trực tiếp

Trong Spring Framework, sau khi kích hoạt xử lý `@Async` (thường bằng `@EnableAsync`), nếu một phương thức được gọi **qua Spring proxy**, không ghi qualifier trong `@Async` và không có executor mặc định cấu hình tường minh, bộ xử lý async tìm executor theo thứ tự:

1. **Tìm một bean `TaskExecutor` có thể xác định được theo kiểu trong `ApplicationContext`.** Nếu có, dùng bean đó, dù tên bean không phải `taskExecutor`.
2. **Nếu bước 1 không chọn được, tìm một bean có tên chính xác `taskExecutor` và có kiểu `java.util.concurrent.Executor`.** Nếu tìm được, dùng bean này. Bean `ThreadPoolTaskExecutor` cũng hợp lệ vì nó triển khai cả hai interface.
3. **Nếu không giải quyết được cả hai, Spring sử dụng một `SimpleAsyncTaskExecutor` dự phòng cục bộ** để thực thi lời gọi `@Async`.

Điểm quyết định là **tìm theo kiểu trước, theo tên sau**. Không phải cứ có một bean bất kỳ tên `taskExecutor` thì nó luôn thắng mọi `TaskExecutor` khác; cũng không phải mọi `Executor` bất kỳ đều được tự động chọn.

Quy tắc trên được mô tả trong Javadoc chính thức của `@EnableAsync` và `AsyncExecutionAspectSupport`. Nó nói về **default executor của xử lý `@Async` trong Spring Framework**; các integration khác như Spring MVC async request hay WebFlux có thể dùng quy tắc chọn executor riêng.

## 2. Điều kiện để cơ chế này thực sự được áp dụng

Trước khi bàn về lựa chọn executor, phải có một lời gọi `@Async` được Spring chặn:

~~~java
@Configuration
@EnableAsync
class AsyncSupportConfiguration {
}
~~~

Đây là **đoạn cấu hình Spring tích hợp**, cần các import `@Configuration` và `@EnableAsync`; không phải chương trình Java chạy độc lập. `@EnableAsync` bật async method advice trong **ApplicationContext tương ứng**. Nó không đồng nghĩa với việc Spring tự thêm một bean `ThreadPoolTaskExecutor` có queue và kích thước pool do bạn mong muốn.

Trong chế độ `AdviceMode.PROXY` mặc định:

- Caller phải gọi phương thức thông qua **bean proxy của Spring**, thường từ một bean khác đã inject service.
- `this.sendAsync()` gọi nội bộ trong cùng instance bỏ qua proxy; annotation có thể không hoạt động, nên không có quá trình tìm executor ở lời gọi đó.
- Phương thức `private` hoặc `final` không phải điểm chặn phù hợp cho class-based proxy thông thường; tránh dựa vào cấu hình proxy không hỗ trợ phương thức đó.
- Không dùng `@Async` trực tiếp cho các phương thức khai báo bên trong `@Configuration` class. Đặt tác vụ vào service bean.
- Nếu ứng dụng có nhiều context, `@EnableAsync` áp dụng tại context được bật, không mặc nhiên kích hoạt mọi context con/cha.

Khi đã có lời gọi thực sự qua interceptor, Spring mới chọn executor để nộp công việc. Gọi trực tiếp `executor.submit(...)` là cơ chế khác: caller đã tự chọn executor, không tham gia thuật toán mặc định của `@Async`.

## 3. Sơ đồ tìm kiếm khi @Async không chỉ rõ executor

~~~text
Caller ---> Spring proxy ---> async interceptor
                                      |
                         @Async có tên/qualifier?
                           | CÓ              | KHÔNG
                           v                  v
                 Tìm bean Executor      Có AsyncConfigurer
                 theo tên/qualifier     cung cấp default?
                           |                  | CÓ
                           v                  v
                     Dùng bean đó       Dùng executor cấu hình
                                              |
                                              | KHÔNG
                                              v
                                   Tìm TaskExecutor theo kiểu
                                              |
                                  +-----------+----------+
                                  | có thể chọn           | không
                                  v                       v
                            Dùng TaskExecutor     Tìm bean "taskExecutor"
                                                          kiểu Executor
                                                      /            \
                                                    có              không
                                                    |                |
                                                    v                v
                                                Dùng bean      SimpleAsyncTaskExecutor
~~~

Sơ đồ mô tả **ưu tiên logic**, không phải pseudocode nội bộ đầy đủ. Cơ chế thực tế có thêm các nhánh xử lý bean không tồn tại, nhiều ứng viên, qualifier sai, cache và cấu hình `BeanFactory`. Một qualifier được chỉ rõ mà không giải quyết được thường dẫn đến **lỗi tra cứu bean**, không nên giả định nó âm thầm quay về default.

## 4. Bước 1: ưu tiên một TaskExecutor có thể chọn theo kiểu

`org.springframework.core.task.TaskExecutor` là abstraction Spring, mở rộng `java.util.concurrent.Executor`. Những implementation thông dụng gồm `ThreadPoolTaskExecutor`, `SimpleAsyncTaskExecutor` hoặc `ConcurrentTaskExecutor`.

Ví dụ một context chỉ có một bean kiểu `TaskExecutor`:

~~~java
@Bean("reportPool")
ThreadPoolTaskExecutor reportPool() {
    ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(4);
    pool.setMaxPoolSize(8);
    pool.setQueueCapacity(50);
    pool.setThreadNamePrefix("report-");
    return pool;
}
~~~

Đây là **một phương thức @Bean minh họa** đặt trong `@Configuration`; Spring quản lý việc khởi tạo và shutdown pool. Vì `reportPool` là ứng viên `TaskExecutor` duy nhất, `@Async` không tên sẽ chọn nó theo kiểu, **dù tên bean là `reportPool`**. Cấu hình này không cần đặt tên `taskExecutor` để được nhận diện.

Nếu có nhiều bean kiểu `TaskExecutor`, phép tìm theo kiểu có thể trở nên không xác định. Cơ chế `BeanFactory` có thể lựa chọn ứng viên ưu tiên (chẳng hạn theo `@Primary` khi áp dụng), nhưng nếu vẫn mơ hồ, Spring chuyển sang thử tên `taskExecutor`.

Không nên suy ra rằng `@Primary` trên một bean bất kỳ kiểu `Executor` sẽ được chọn giống một `TaskExecutor` duy nhất: **bước đầu tìm `TaskExecutor`**, rồi mới đến bean `Executor` theo tên.

## 5. Bước 2: bean tên taskExecutor làm đường dự phòng

Nếu tìm theo kiểu không chọn được, Spring tìm bean với tên **chính xác**:

~~~text
taskExecutor
~~~

Bean đó phải tương thích với `java.util.concurrent.Executor`. Tên này phân biệt với các tên như `tasksExecutor`, `myTaskExecutor`, `applicationTaskExecutor` hay `asyncExecutor`.

Ví dụ khi có nhiều `TaskExecutor` và muốn chỉ định default ổn định mà không thêm `AsyncConfigurer`:

~~~java
@Bean("ioPool")
ThreadPoolTaskExecutor ioPool() {
    return poolWithPrefix("io-");
}

@Bean("cpuPool")
ThreadPoolTaskExecutor cpuPool() {
    return poolWithPrefix("cpu-");
}

@Bean("taskExecutor")
ThreadPoolTaskExecutor defaultAsyncPool() {
    return poolWithPrefix("default-");
}
~~~

Đây là **đoạn minh họa tích hợp**: hàm `poolWithPrefix` thuộc ứng dụng và không được định nghĩa trong snippet; ví dụ hoàn chỉnh chạy được ở mục 8. Khi nhiều pool kiểu `TaskExecutor` cùng tồn tại mà không có ứng viên ưu tiên theo type, `@Async` không ghi tên có thể chọn bean `taskExecutor` trong bước tra cứu thứ hai.

Cũng cần chú ý: bean theo tên `taskExecutor` **có thể là JDK Executor hoặc ExecutorService**, không bắt buộc phải là Spring `TaskExecutor`. Interceptor có cơ chế thích ứng với executor gốc khi cần. Ngược lại, một bean có đúng tên nhưng không triển khai `Executor` là cấu hình không hợp lệ, có thể gây lỗi kiểu bean; đừng trông đợi fallback an toàn trong trường hợp cấu hình sai kiểu.

**Nếu có cả một `TaskExecutor` được chọn theo kiểu và một bean `Executor` tên `taskExecutor` khác**, bước tìm theo kiểu được ưu tiên. Đây là nguyên nhân phổ biến khiến chỉ đổi tên bean vẫn chưa thay đổi pool thực thi như mong muốn.

## 6. Bước 3: không tìm thấy thì SimpleAsyncTaskExecutor

Khi không có executor mặc định được cấu hình và cả hai bước tra cứu đều không chọn được, `@EnableAsync` dùng `SimpleAsyncTaskExecutor` dự phòng. Đây là executor thực sự chạy tác vụ bất đồng bộ, **không phải trường hợp Spring bỏ qua @Async**.

Đặc điểm cần nhớ:

- `SimpleAsyncTaskExecutor` tạo **thread mới cho mỗi task** trong cách dùng thông thường, **không tái sử dụng thread như thread pool**.
- Concurrency mặc định của loại này không có giới hạn hữu hạn do bạn thiết lập. Nếu nhiều request cùng kích hoạt hàng nghìn task chậm, số thread có thể tăng nhanh và gây áp lực bộ nhớ, scheduler và downstream.
- Nó có lựa chọn giới hạn concurrency và, trên JDK 21+, lựa chọn virtual threads; nhưng việc được dùng **ngầm định** không có nghĩa đã được tune phù hợp tải sản phẩm.
- Nó không phải `ThreadPoolTaskExecutor` mặc định với `corePoolSize=...`, `maxPoolSize=...` hoặc `queueCapacity=...`. Không thể dùng các thuộc tính pool đó để suy đoán hành vi fallback.
- Executor dự phòng được tạo cho cơ chế interceptor, không tương đương một bean pool do ứng dụng quản lý, giám sát và shutdown theo lifecycle chung.

**Rủi ro thực tế:** một ứng dụng có hai pool riêng, `ioPool` và `cpuPool`, nhưng không có bean tên `taskExecutor` và không có default rõ ràng. Người phát triển tưởng `@Async` tự chọn pool “hợp lý” giữa chúng. Trong khi đó, nó có thể dùng `SimpleAsyncTaskExecutor` cục bộ. Vì vậy nên khai báo lựa chọn default tường minh, theo dõi log và xác minh thread/pool thực tế.

## 7. Ma trận tình huống cần phân biệt

| Bean/config trong một context Spring Framework | `@Async` không qualifier chọn gì? | Lý do |
| --- | --- | --- |
| Chỉ có `ThreadPoolTaskExecutor` tên `reportPool` | `reportPool` | Một `TaskExecutor` chọn được theo kiểu |
| Có nhiều `TaskExecutor`, không ứng viên ưu tiên, có `Executor` tên `taskExecutor` | Bean tên `taskExecutor` | Tra cứu type mơ hồ; dùng tên fallback |
| Có nhiều `TaskExecutor`, không ứng viên ưu tiên, không bean `taskExecutor` | `SimpleAsyncTaskExecutor` dự phòng | Không thể chọn type hoặc name |
| Không có `TaskExecutor`, chỉ có `ExecutorService` tên `backgroundPool` | `SimpleAsyncTaskExecutor` dự phòng | Một raw `Executor` tên tùy ý không đủ cho bước 1 hoặc 2 |
| Không có `TaskExecutor`, có `ExecutorService` tên `taskExecutor` | Bean `taskExecutor` | Bước tìm theo tên cho phép kiểu `Executor` |
| Có một `TaskExecutor` chọn được và một raw `Executor` tên `taskExecutor` | `TaskExecutor` được chọn theo kiểu | Lookup type diễn ra trước |
| Có `AsyncConfigurer.getAsyncExecutor()` trả executor cụ thể | Executor do `AsyncConfigurer` cung cấp | Đã cấu hình default tường minh |
| Method ghi `@Async("reportPool")` | Bean theo tên/qualifier `reportPool` | Override default ở cấp phương thức |

**Điểm về @Primary:** khi có nhiều ứng viên `TaskExecutor`, `BeanFactory` có thể áp dụng quy tắc lựa chọn ứng viên như `@Primary`. Vì thế câu “nhiều `TaskExecutor` thì **luôn** dùng bean tên `taskExecutor`” là sai. Xác nhận cách bean được chọn trong ứng dụng cụ thể; ưu tiên khai báo `AsyncConfigurer` hoặc qualifier rõ ràng khi có nhiều pool.

## 8. Ví dụ Spring Framework + Java 17 chạy được: ba kịch bản lookup

Ví dụ sau dùng Java 17+, Maven, Spring Framework **6.2.9**. Nó tạo ba `ApplicationContext` riêng để không làm các bean của từng kịch bản ảnh hưởng nhau:

1. Một `TaskExecutor` duy nhất tên `analyticsPool` được chọn dù không có tên `taskExecutor`.
2. Có ba `TaskExecutor`, trong đó một bean tên `taskExecutor`; Spring chọn bean tên đó khi lookup theo kiểu mơ hồ.
3. Không có bean executor nào; Spring dùng fallback chạy trên một thread khác caller.

Mỗi trường hợp gọi `Probe.threadName()` **thông qua Spring bean proxy** rồi đợi `CompletableFuture`. Chúng ta không phụ thuộc vào thứ tự scheduling giữa task.

### Cấu trúc project

~~~text
spring-async-lookup-demo/
├── pom.xml
└── src/main/java/demo/ExecutorLookupDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-async-lookup-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/ExecutorLookupDemo.java

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ExecutorLookupDemo {
    public static class Probe {
        @Async
        public CompletableFuture<String> threadName() {
            return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
        }
    }

    private static ThreadPoolTaskExecutor pool(String prefix) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(4);
        executor.setThreadNamePrefix(prefix);
        return executor;
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class UniqueConfig {
        @Bean public Probe probe() { return new Probe(); }
        @Bean public ThreadPoolTaskExecutor analyticsPool() {
            return pool("unique-");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class NamedConfig {
        @Bean public Probe probe() { return new Probe(); }
        @Bean public ThreadPoolTaskExecutor firstPool() {
            return pool("first-");
        }
        @Bean public ThreadPoolTaskExecutor secondPool() {
            return pool("second-");
        }
        @Bean("taskExecutor")
        public ThreadPoolTaskExecutor preferredPool() {
            return pool("named-");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class MissingConfig {
        @Bean public Probe probe() { return new Probe(); }
    }

    private static String runIn(Class<?> configClass) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(configClass)) {
            return context.getBean(Probe.class)
                    .threadName()
                    .get(5, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        String callerThread = Thread.currentThread().getName();
        System.out.println("Unique TaskExecutor: " +
            runIn(UniqueConfig.class).startsWith("unique-"));
        System.out.println("Named taskExecutor: " +
            runIn(NamedConfig.class).startsWith("named-"));
        System.out.println("Fallback runs elsewhere: " +
            !runIn(MissingConfig.class).equals(callerThread));
    }
}
~~~

Chạy trong thư mục `spring-async-lookup-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ExecutorLookupDemo
~~~

Các dòng **stdout do chương trình tự in ra**:

~~~text
Unique TaskExecutor: true
Named taskExecutor: true
Fallback runs elsewhere: true
~~~

Khi rơi vào kịch bản fallback, Spring **có thể in thêm log thông tin** về việc không tìm thấy `TaskExecutor` hay bean tên `taskExecutor`; đó là log framework, không phải dòng `System.out.println` của ví dụ. Ví dụ đã được **biên dịch với mục tiêu Java 17 và chạy trên OpenJDK 24**, ba dòng stdout được đối chiếu đúng. Các giá trị `core=1`, `max=2`, `queue=4` chỉ phục vụ test, không phải mặc định production.

Giải thích vì sao kết quả đáng tin:

- Từng context độc lập nên thuật toán chỉ nhìn thấy các bean của chính kịch bản đó.
- `@EnableAsync` bật proxy tại cả ba context; `Probe` là bean được tạo và lấy từ Spring, không dùng `new Probe().threadName()` trong caller.
- `@Async` không ghi tên nên cả ba đều chạy thuật toán default.
- `CompletableFuture.completedFuture(...)` được tạo **bên trong worker**; proxy trả cho caller một future thực sự đại diện việc thực thi async. `get(5, SECONDS)` là điều kiện chờ để kiểm tra kết quả.
- Prefix `unique-` và `named-` phân biệt rõ executor đã chọn. Trường hợp không có bean executor được kiểm tra bằng việc thread khác caller; không cố ghim prefix của executor dự phòng.
- `try`-with-resources đóng `AnnotationConfigApplicationContext`, nên các `ThreadPoolTaskExecutor` được khai báo `@Bean` có lifecycle do Spring quản lý.

## 9. Khi nào chuyển từ lookup mặc định sang lựa chọn tường minh?

Thuật toán của bài này chỉ áp dụng khi lời gọi `@Async` qua proxy **không chỉ định tên** và không có default từ `AsyncConfigurer`. Nếu muốn method luôn dùng pool I/O, ghi `@Async("ioExecutor")` và bảo đảm bean tương thích tồn tại. Khi nhiều method không qualifier cần cùng một default, có thể implement `AsyncConfigurer.getAsyncExecutor()` trả một bean executor đã được Spring quản lý.

Ví dụ phân biệt tại điểm gọi: `@Async` dùng nhánh lookup theo kiểu/tên/fallback; `@Async("billingExecutor")` chọn bean hoặc qualifier đó; `CompletableFuture.supplyAsync(...)` trong mã Java thuần lại dùng executor được truyền hoặc mặc định của JDK, không tham gia lookup Spring.

Đừng tạo một pool mới cho mỗi request. Với executor tự tạo ngoài `@Bean`, ứng dụng phải quản lý initialize/shutdown; với bean Spring nên để container xử lý lifecycle. Mục tiêu vận hành là chọn pool có giới hạn, quan sát được và không phụ thuộc vào fallback khó kiểm soát.

## 10. Đặc biệt: Spring Boot có thể đã tạo Executor trước đó

**Spring Framework thuần** và **Spring Boot auto-configuration** là hai lớp cơ chế khác nhau.

Trong **Spring Boot 3.5** làm ví dụ, khi không có bean `Executor` phù hợp do ứng dụng tự khai báo, Boot thường auto-configure một bean `AsyncTaskExecutor`:

- Thông thường là `ThreadPoolTaskExecutor` với cấu hình Boot cung cấp.
- Khi dùng Java 21+ và bật virtual threads, Boot có thể dùng `SimpleAsyncTaskExecutor` gắn virtual threads.
- Bean auto-configured thường tên `applicationTaskExecutor` và có thể được `@Async` dùng qua lookup theo kiểu, **không cần phải đổi tên thành `taskExecutor`**.
- Khi có bean `Executor` do ứng dụng cung cấp, auto-configuration có thể back off; phải đọc **phiên bản Spring Boot và cấu hình thực tế** để kết luận executor nào còn tồn tại.
- Spring MVC, WebFlux, GraphQL và các integration khác có thể yêu cầu bean tên `applicationTaskExecutor` với loại cụ thể; tên đó có ý nghĩa riêng, không đồng nhất với fallback `taskExecutor` của Spring Framework.

Do vậy không nên ghi “không cấu hình gì thì `@Async` chắc chắn dùng SimpleAsyncTaskExecutor” cho **mọi Spring Boot app**. Đó là kết luận đúng cho lookup Framework khi thực sự không có default executor hay bean phù hợp, nhưng Boot có thể tạo ra một executor trước khi thuật toán được thực thi.

Hãy phân biệt thêm: `@EnableAsync` kích hoạt annotation-based async; `spring.task.execution.*` là cấu hình Boot cho executor được Boot quản lý khi auto-configuration tương ứng áp dụng. Có property nhưng bean executor thực tế là bean tùy chỉnh hoặc fallback thì property đó có thể không ảnh hưởng như kỳ vọng.

## 11. Một số trường hợp dễ chọn nhầm

### 11.1. Nhiều TaskExecutor nhưng không ai tên taskExecutor

~~~text
@Bean("emailPool")     ThreadPoolTaskExecutor
@Bean("reportPool")    ThreadPoolTaskExecutor
Không có @Primary hoặc AsyncConfigurer
Không có bean tên taskExecutor
~~~

Đây là mô tả tình huống, không phải code Java hoàn chỉnh. Nếu lookup theo kiểu không phân giải được, Spring không tự bốc ngẫu nhiên `emailPool` hay `reportPool`; nó tìm theo tên `taskExecutor` rồi có thể dùng `SimpleAsyncTaskExecutor` fallback. **Sửa:** đặt tên/qualifier rõ ràng, chọn default bằng `AsyncConfigurer`, hoặc thiết kế ứng viên mặc định có thể xác định được.

### 11.2. Có bean tên taskExecutor nhưng cũng có ứng viên type phù hợp khác

~~~text
TaskExecutor bean: paymentPool (ứng viên duy nhất theo type)
Executor bean: taskExecutor (không implement TaskExecutor)
~~~

Nếu `paymentPool` là ứng viên kiểu `TaskExecutor` duy nhất, nó được chọn **trước** bean tên `taskExecutor`. Đổi tên bean thứ hai không tự làm thay đổi luật ưu tiên. **Sửa:** chọn tên tường minh tại method hoặc cấu hình `AsyncConfigurer`.

### 11.3. Không có @EnableAsync hoặc gọi self-invocation

Nếu `@Async` không được kích hoạt hoặc lời gọi không đi qua proxy, phương thức có thể chạy **đồng bộ trên caller thread**. Đừng chẩn đoán đây là “Spring tìm sai executor”; lúc này interceptor còn chưa tham gia vào lời gọi.

### 11.4. Tạo ExecutorService rồi cho rằng Spring sẽ tự chọn

Một `ExecutorService` bean tên `myExecutor` chỉ là `Executor` JDK, không nhất thiết là `TaskExecutor` Spring. Không có bean `TaskExecutor` nào và bean đó cũng không tên `taskExecutor`, thuật toán default Framework không tự chọn `myExecutor`. **Sửa:** dùng tên `taskExecutor`, `AsyncConfigurer`, hoặc `@Async("myExecutor")`.

### 11.5. Tưởng ứng dụng chỉ có một Spring ApplicationContext

Trong ứng dụng web có parent/child context, bean nằm ở context khác hoặc annotation chỉ bật ở một context có thể làm kết quả tra cứu khác dự kiến. Hãy xác nhận chính context chứa interceptor/bean được xử lý và những executor bean nó có thể nhìn thấy.

## 12. Cách xác nhận executor thật ở runtime

Đọc cấu hình là bước đầu; kiểm thử thread và metric là cách chứng minh lựa chọn được áp dụng:

1. **Tạo thread name prefix đặc trưng** cho từng `ThreadPoolTaskExecutor`: `email-`, `billing-`, `report-`. Trong task, log `Thread.currentThread().getName()` kèm operation ID.
2. **Lấy bean qua Spring context**, gọi `@Async` từ bên ngoài bean chứa method và quan sát kết quả; không tạo object bằng `new` trong test.
3. **Kiểm tra type và name:** liệt kê ứng viên `TaskExecutor`, bean `Executor` tên `taskExecutor`, `AsyncConfigurer` và qualifier tại method/class. Khi sử dụng Spring Boot, kiểm tra cả `applicationTaskExecutor` và auto-configuration.
4. **Bật log phù hợp** để thấy thông báo khi fallback; một số phiên bản ghi log kiểu “No task executor bean found for async processing” khi không tìm thấy bean.
5. **Xem metric pool:** active worker, core/max, queue size, rejected tasks và thread-name prefix. Nếu `@Async` thực sự chạy qua pool cụ thể, metric và thread name phải nhất quán.
6. **Kiểm tra overload:** với `ThreadPoolTaskExecutor`, việc nộp task có thể bị từ chối khi bão hòa; với `SimpleAsyncTaskExecutor` fallback không giới hạn concurrency mặc định, profile tải có thể rất khác.

Không nên dùng **chỉ** tên luồng `main` trong log để kết luận thiếu proxy: executor có thể dùng `CallerRunsPolicy` để chạy task trên caller thread khi quá tải. Kết hợp config, proxy, thread names, metric và một test không bão hòa để phân biệt.

## 13. Chọn executor đúng chưa đủ để bảo đảm nghiệp vụ

Khi đã biết Spring nộp `@Async` vào executor nào, còn những hợp đồng riêng phải thiết kế:

- **Exception:** method trả `CompletableFuture`/`Future` cho phép caller theo dõi completion và failure. Với `@Async void`, exception không quay về stack của caller; Spring có `AsyncUncaughtExceptionHandler` (mặc định thường log).
- **Rejection:** queue đầy/executor shutdown có thể khiến lời gọi nộp task thất bại ngay; phương thức nghiệp vụ vẫn chưa được xử lý trong worker. Cần backpressure, xử lý lỗi và retry có giới hạn nếu phù hợp.
- **Transaction:** với giao dịch imperative, transaction gắn với worker thread; không tự truyền transaction đang mở của HTTP request sang thread async. Cần ranh giới transaction ở worker nếu có thao tác DB.
- **Thread safety:** singleton bean có thể bị nhiều request gọi cùng lúc; việc chọn pool không bảo vệ shared mutable state.
- **Execution context:** `ThreadLocal`, MDC, security/request context không tự được bảo đảm truyền vào worker. Dùng cơ chế propagation phù hợp, dọn context đúng cách và truyền command immutable khi có thể.
- **Ordering và delivery:** thread pool không bảo đảm xử lý đúng thứ tự nộp hoặc chỉ một lần trên nhiều instance. `@Async` không làm công việc tồn tại qua crash; yêu cầu bền vững cần job store/queue/idempotency.
- **Lifecycle:** `ThreadPoolTaskExecutor` do Spring quản lý có hook shutdown/configuration; local fallback không tương đương một pool bean do ứng dụng quan sát được.

Nếu workload gồm nhiều công việc blocking I/O, CPU-bound và thao tác có rủi ro khác nhau, nên dùng executor được **chọn rõ** cho từng nhóm thay vì phụ thuộc vào tên mặc định khó kiểm soát.

## 14. Kiểm thử không mơ hồ

Bộ kiểm thử tích hợp hữu ích cho chủ đề này nên có:

1. **Một TaskExecutor:** đăng ký một bean với prefix riêng, gọi `@Async` không tên; assert thread name mang prefix đó.
2. **Nhiều TaskExecutor + taskExecutor:** đăng ký nhiều ứng viên type và một bean tên `taskExecutor`; assert đúng prefix tên fallback.
3. **Không có ứng viên:** context chỉ có `@EnableAsync` + service; assert task chạy ở thread khác caller, nhận biết thông báo fallback nếu có.
4. **@Async explicit qualifier:** khai báo `@Async("ioExecutor")` và default khác; assert chọn io executor.
5. **Self-invocation:** gọi qua `this` để minh họa không đi qua proxy trong default proxy mode; test phải tách khỏi bài test async thật.
6. **ApplicationContext riêng:** tránh lẫn bean của kịch bản trước, không để auto-configuration của Boot làm biến đổi bài test Framework thuần.
7. **Failure và overload:** khi pool bounded bão hòa, assert chính sách từ chối và cách caller xử lý; khi task ném lỗi, assert Future/handler nhận đúng lỗi.

Các test kiểu này xác thực điều quan trọng là **executor thực sự được chọn**, không chỉ kiểm tra bean tồn tại. Ví dụ ở mục 8 minh họa ba kịch bản trung tâm mà không cần so sánh thread-name cụ thể của fallback.

## 15. Checklist cấu hình @Async an toàn

- Tôi biết `@EnableAsync` được bật ở context nào và lời gọi đã đi qua Spring proxy.
- Tôi biết method có qualifier `@Async("...")` hoặc có `AsyncConfigurer` hay không.
- Tôi kiểm kê được các bean kiểu `TaskExecutor` và xác định liệu lookup type có duy nhất/ưu tiên rõ ràng.
- Tôi kiểm tra chính xác bean tên `taskExecutor`, kiểu phải là `Executor`.
- Tôi không suy ra `applicationTaskExecutor` của Boot giống hệt fallback `taskExecutor` của Framework.
- Tôi không phụ thuộc vào `SimpleAsyncTaskExecutor` fallback cho luồng tải sản phẩm chưa được giới hạn.
- Tôi chủ động thiết kế core/max/queue/rejection, shutdown và metric nếu sử dụng thread pool.
- Tôi phân biệt task đã được nộp với task đã hoàn thành thành công.
- Tôi kiểm soát exception, transaction, context propagation và shared mutable state của tác vụ.
- Tôi xác minh bằng một integration test và log thread prefix thay vì chỉ nhìn annotation.

**Kết luận:** Khi `@Async` được bật và không có cấu hình executor tường minh, Spring Framework ưu tiên **`TaskExecutor` theo kiểu**, sau đó **`Executor` có tên `taskExecutor`**, cuối cùng dùng **`SimpleAsyncTaskExecutor` dự phòng**. Trong Spring Boot, auto-configuration có thể tạo sẵn executor nên cần kiểm tra context thực tế trước khi kết luận.

## Tài liệu tham khảo chính thức

- [Spring Framework – EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): thuật toán tìm executor, fallback, proxy và AsyncConfigurer.
- [Spring Framework – AsyncExecutionAspectSupport Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/AsyncExecutionAspectSupport.html): lookup theo type/name và lựa chọn executor cho từng method.
- [Spring Framework – Async Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html): qualifier ở method/class, kiểu trả về `Future` và `CompletableFuture`.
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): bật `@Async`, qualifier và quản lý exception.
- [Spring Framework – SimpleAsyncTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/SimpleAsyncTaskExecutor.html): tạo thread, giới hạn concurrency và lifecycle.
- [Spring Boot 3.5 – Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): `applicationTaskExecutor`, auto-configuration và tương tác `@EnableAsync`.
