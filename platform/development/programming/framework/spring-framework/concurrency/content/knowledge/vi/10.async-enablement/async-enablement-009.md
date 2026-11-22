# Vai trò của `AsyncAnnotationBeanPostProcessor` trong Spring Framework

## Mục tiêu

Viết `@Async` trên một phương thức **chưa đủ** để việc thực thi tự chuyển sang thread khác. Spring cần phát hiện annotation trên bean được quản lý, tạo hoặc bổ sung AOP proxy và gắn logic chuyển lời gọi vào executor. Trong chế độ mặc định của `@EnableAsync`, hạ tầng giữ vai trò then chốt ở bước này là **`org.springframework.scheduling.annotation.AsyncAnnotationBeanPostProcessor`**.

Bài học giải thích chính xác processor làm việc **khi nào**, nó tạo ra **thành phần gì**, và phân biệt trách nhiệm của nó với phần thực sự **gửi và chạy task**. Sau khi học, bạn có thể:

1. Mô tả đường đi từ `@EnableAsync` tới việc đăng ký `AsyncAnnotationBeanPostProcessor`.
2. Giải thích vì sao `BeanPostProcessor` thêm `AsyncAnnotationAdvisor` vào proxy cho bean có `@Async`.
3. Phân biệt bước xử lý bean khi khởi tạo với bước interception khi phương thức được gọi.
4. Lần theo việc chọn executor, tạo `Future`/`CompletableFuture`, xử lý `void` và exception.
5. Biết giới hạn của proxy mode: self-invocation, object tạo bằng `new`, method không thể được proxy, kiểu proxy JDK/CGLIB và phạm vi application context.
6. Tự chạy ví dụ Java 17+ xác nhận infrastructure processor đã đăng ký, service là AOP proxy và logic chạy trong executor được chọn.

**Một câu cần nhớ:** `AsyncAnnotationBeanPostProcessor` **thiết lập đường đi bất đồng bộ cho bean Spring**; nó **không phải thread pool** và không tự thực thi từng task. Khi ứng dụng gọi phương thức qua proxy, interceptor/advice mới gửi lời gọi tới executor.

## 1. Ba thời điểm dễ bị trộn lẫn

Để hiểu `@Async`, hãy tách ba giai đoạn:

| Thời điểm | Thành phần tham gia | Việc xảy ra |
| --- | --- | --- |
| **Khai báo cấu hình** | `@Configuration`, `@EnableAsync`, `AsyncConfigurationSelector`, `ProxyAsyncConfiguration` | Spring import cấu hình hạ tầng async và đăng ký bean processor trong context áp dụng. |
| **Khởi tạo bean** | `AsyncAnnotationBeanPostProcessor`, `AsyncAnnotationAdvisor`, AOP proxy infrastructure | Khi bean Spring được xử lý, processor gắn advisor async vào proxy có sẵn hoặc tạo proxy nếu bean có annotation phù hợp. |
| **Lúc phương thức được gọi** | Caller, AOP proxy, async interceptor, `Executor`/`TaskExecutor`, worker | Interceptor nhận lời gọi qua proxy, xác định executor, gửi công việc; worker mới thực thi thân phương thức và xử lý kết quả/lỗi. |

Có thể hình dung:

```text
          KHỞI TẠO APPLICATION CONTEXT
@Configuration + @EnableAsync
       |
       v
AsyncConfigurationSelector (proxy mode)
       |
       v
ProxyAsyncConfiguration đăng ký AsyncAnnotationBeanPostProcessor
       |
       v
Bean được tạo -> BeanPostProcessor kiểm tra @Async
       |
       v
Bean proxy có AsyncAnnotationAdvisor/async advice
       |
       +----------- CHỜ LỜI GỌI THỰC TẾ ------------+
                                                     |
             LÚC CHẠY                               v
Caller -> service proxy -> async interceptor -> chọn executor
                                        |
                                        v
                                 submit invocation
                                        |
                                        v
                                worker chạy method
                                        |
                                        v
                              value / error / completion
```

Processor không tự lập lịch định kỳ, không gọi method ngay khi context khởi động và không mặc định tạo một thread cho mỗi bean. Công việc chỉ được gửi khi có lời gọi phù hợp đi qua proxy.

## 2. `@EnableAsync` đăng ký processor như thế nào?

Trong Spring Framework, `@EnableAsync` kích hoạt hỗ trợ annotation-driven asynchronous method execution cho **application context nơi nó được khai báo**.

Cấu hình tối thiểu:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
```

Đây là đoạn cấu hình trong một dự án Spring, chưa phải chương trình độc lập. Ở `AdviceMode.PROXY` (mặc định), `@EnableAsync` import `AsyncConfigurationSelector`; selector chọn cấu hình hạ tầng `ProxyAsyncConfiguration`, từ đó đăng ký một `AsyncAnnotationBeanPostProcessor`.

Trong cơ chế này, processor có một bean name **nội bộ** dùng bởi Spring, tương ứng hằng số trong `TaskManagementConfigUtils`. Tên nội bộ hữu ích để debug container, nhưng mã nghiệp vụ không nên phụ thuộc vào tên hạ tầng nếu chỉ cần `@Async`.

Điều kiện cần nhớ:

- `@EnableAsync` cần được thực thi qua cấu hình trong **đúng application context**. Nếu hệ thống có root context và nhiều servlet child context, kích hoạt ở một context không đồng nghĩa các context khác được bật.
- Nếu dùng Spring Boot, auto-configuration cụ thể có thể khác nhau theo dự án; không suy đoán chỉ vì có dependency `spring-context` hoặc annotation trên service thì async đã được bật.
- `@EnableAsync` **không tạo nghiệp vụ** và không biến mọi method thành async. Bean có phương thức được annotation phù hợp mới có advisor tương ứng.
- `@EnableAsync(mode = AdviceMode.ASPECTJ)` chọn hướng xử lý khác, cần `spring-aspects` và weaving; lúc đó cách chặn lời gọi không dựa trên AOP proxy do bean post-processor ở chế độ proxy tạo ra. Không dùng cách kiểm chứng `AopUtils.isAopProxy` làm điều kiện bắt buộc cho AspectJ mode.

Hai tên gần nhau nhưng nhiệm vụ khác:

| Thành phần | Vai trò |
| --- | --- |
| `@EnableAsync` | Bật và cấu hình cơ chế annotation-driven async. |
| `AsyncConfigurationSelector` / `ProxyAsyncConfiguration` | Chọn và đăng ký các bean hạ tầng khi ở proxy mode. |
| **`AsyncAnnotationBeanPostProcessor`** | Phát hiện async annotation trên Spring bean và bổ sung advisor/proxy cho đường gọi. |
| `AsyncAnnotationAdvisor` | Tập hợp pointcut xác định lời gọi cần chặn và advice thực hiện logic async. |
| `AnnotationAsyncExecutionInterceptor` | Advice/interceptor giải quyết executor theo annotation và gửi lời gọi để thực thi. |
| `Executor` / `TaskExecutor` | Thực sự thực hiện hoặc phân phối task đến worker theo chính sách cụ thể. |

Tên lớp và cách chia trách nhiệm ở bảng này dựa trên hạ tầng Spring Framework 6.2; đây là kiến thức để đọc luồng thực thi, không phải yêu cầu mọi ứng dụng phải tự tạo các lớp infrastructure.

## 3. BeanPostProcessor làm gì khi bean được khởi tạo?

`BeanPostProcessor` là extension point của Spring IoC container cho phép xử lý bean trong quá trình container tạo và cấu hình chúng. `AsyncAnnotationBeanPostProcessor` mở rộng hạ tầng AOP post-processing, vì vậy công việc chính là **trang bị proxy/advisor**, không phải chạy method nghiệp vụ.

Với một bean như sau:

```java
@Service
public class EmailService {
    @Async("mailExecutor")
    public CompletableFuture<String> send(String address) {
        return CompletableFuture.completedFuture("accepted:" + address);
    }
}
```

Đây là **ví dụ một lớp** trong ứng dụng đã có `@EnableAsync`, `@Service` scanning và bean `mailExecutor`; không phải Java file chạy độc lập.

Trước khi ứng dụng gọi `send`, Spring có thể đã:

1. Tạo instance gốc của `EmailService` theo định nghĩa bean.
2. Đưa bean qua chuỗi post-processors trong giai đoạn khởi tạo container.
3. Để `AsyncAnnotationBeanPostProcessor` tạo một `AsyncAnnotationAdvisor` phù hợp với annotation trên lớp hoặc phương thức.
4. Bổ sung advisor vào AOP proxy hiện có hoặc tạo proxy cho bean đủ điều kiện; đối tượng ứng dụng inject thường là **điểm tham chiếu proxy**.
5. Trả bean đã xử lý về nơi inject hoặc `ApplicationContext.getBean(...)`.

Trong những trường hợp đơn giản, `EmailService` không khai báo interface nên Spring có thể dùng class-based proxy. Nếu nó triển khai interface và cấu hình mặc định ưa JDK proxy, object được trả có thể chỉ expose interface của service. Vì vậy khi debug, đừng giả định lúc nào `getBean(ConcreteClass.class)` cũng hợp lệ trong ứng dụng dùng JDK dynamic proxies.

Việc **chỉ có annotation trong source** chưa đảm bảo lời gọi được chặn. Annotation cần được hạ tầng Spring nhận ra trên một bean thực sự được quản lý, với method đủ điều kiện để proxy/intercept.

### Processor có sửa code phương thức gốc không?

Không. Trong proxy mode, processor không viết lại bytecode của method nghiệp vụ. Nó xây **đường gọi trung gian**: client gọi proxy, advisor/interceptor xử lý rồi chuyển việc. Đối tượng đích vẫn chứa logic gốc.

Mô hình ngắn:

```text
Client
  |
  v
Proxy (được bổ sung advisor lúc bean initialization)
  |
  +--- advice xử lý async: lập task và gửi executor
                                  |
                                  v
                           Target.method(...)
```

Tách biệt này giải thích vì sao lệnh `this.send(...)` trong cùng target không chạy lại qua proxy.

## 4. `AsyncAnnotationAdvisor` và interceptor: cầu nối tới lúc chạy

`AsyncAnnotationAdvisor` kết hợp hai yếu tố AOP:

- **Pointcut**: quyết định bean/method nào phù hợp với `@Async` hoặc annotation async tùy chỉnh.
- **Advice**: logic thực thi khi lời gọi phù hợp đi qua proxy, gồm xác định executor, tạo task và chuyển công việc.

Spring có `AnnotationAsyncExecutionInterceptor`, một specialization của `AsyncExecutionInterceptor`, để đọc qualifier của `@Async` và xác định executor thích hợp.

Ví dụ:

```java
@Async("reportExecutor")
public CompletableFuture<Report> renderReport(String id) {
    // Phần xử lý thực tế thực thi trong executor được chọn.
}
```

Đây là phần khai báo method minh họa, không phải chương trình Java độc lập; `Report` và thân xử lý do ứng dụng cung cấp.

Khi caller gọi method qua proxy, đường xử lý thường gồm:

1. Interceptor nhận `MethodInvocation` thay vì gọi ngay target.
2. Từ annotation, chọn `reportExecutor` hoặc cơ chế executor mặc định được cấu hình.
3. Tạo task chứa phần lời gọi target.
4. Gửi task đến executor; caller nhận handle trả về theo hợp đồng async.
5. Worker chạy method thật, rồi hoàn tất kết quả hoặc nắm lỗi để caller/handler quan sát.

**Processor không trực tiếp chọn thread mỗi lần**; việc chọn pool có thể được cấu hình qua `AsyncConfigurer`, tên bean từ `@Async` hoặc mặc định, còn chính executor quyết định worker, queue và chính sách từ chối.

Nếu dùng `Executor` thực thi đồng bộ như `Runnable::run`, hoặc policy `CallerRunsPolicy` khi pool bão hòa, một lời gọi có thể chạy trên caller dù đi qua async proxy. Do đó **proxy có advisor** và **thực thi trên thread khác** là hai khẳng định phải kiểm chứng riêng.

## 5. Ví dụ chạy được: kiểm chứng processor, proxy và worker

Ví dụ sau có thể chạy với **JDK 17+**, Maven và **Spring Framework 6.2.12**. Nó xác minh ba tầng khác nhau:

1. Spring đã đăng ký `AsyncAnnotationBeanPostProcessor`.
2. Bean service lấy từ context thực sự là AOP proxy.
3. Lời gọi `@Async("lessonExecutor")` chạy thân method trong worker của executor có prefix `lesson-`, không phải thread caller.

Cấu trúc thư mục:

```text
async-bpp-demo/
├── pom.xml
└── src/main/java/demo/AsyncBppDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-bpp-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                    <mainClass>demo.AsyncBppDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/AsyncBppDemo.java`:

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.AsyncAnnotationBeanPostProcessor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncBppDemo {

    public record WorkResult(String value, Thread executedBy) {
    }

    // Lớp public, không final và method public không final để
    // class-based proxy có thể chặn invocation qua Spring bean.
    public static class WorkService {
        @Async("lessonExecutor")
        public CompletableFuture<WorkResult> process(String input) {
            return CompletableFuture.completedFuture(
                new WorkResult(
                    "done:" + input,
                    Thread.currentThread()
                )
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {
        @Bean
        public WorkService workService() {
            return new WorkService();
        }

        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("lesson-");
            return executor;
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            // Chứng minh BPP hạ tầng do @EnableAsync đăng ký.
            boolean processorRegistered =
                context.getBeanNamesForType(
                    AsyncAnnotationBeanPostProcessor.class).length > 0;

            WorkService service = context.getBean(WorkService.class);
            boolean proxied = AopUtils.isAopProxy(service);
            Thread caller = Thread.currentThread();

            CompletableFuture<WorkResult> handle = service.process("A");
            WorkResult result = handle.get(5, TimeUnit.SECONDS);

            System.out.println("processorRegistered=" + processorRegistered);
            System.out.println("serviceProxied=" + proxied);
            System.out.println("differentThread="
                + (result.executedBy() != caller));
            System.out.println("namedExecutorWorker="
                + result.executedBy().getName().startsWith("lesson-"));
            System.out.println("value=" + result.value());
        }
    }
}
```

Chạy từ thư mục `async-bpp-demo` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

Năm dòng **do chương trình in ra** khi chạy bình thường là:

```text
processorRegistered=true
serviceProxied=true
differentThread=true
namedExecutorWorker=true
value=done:A
```

### Vì sao có thể dự đoán kết quả?

- `@EnableAsync` nằm trên `AppConfig`, vốn được đăng ký trong `AnnotationConfigApplicationContext`. Spring đăng ký BPP async khi khởi động context.
- Bean `WorkService` được tạo bằng `@Bean` và có method public `@Async`. Hạ tầng BPP bổ sung advisor và tạo proxy (class-based do service này không có interface).
- `AopUtils.isAopProxy(service)` quan sát object thực sự được trả cho caller; đó là proxy.
- Caller gọi `service.process("A")` qua proxy, interceptor gửi công việc tới bean `lessonExecutor`.
- `ThreadPoolTaskExecutor` trong ví dụ dùng worker có tên bắt đầu `lesson-` và không dùng `CallerRunsPolicy`; do vậy worker chạy method khác thread caller.
- `WorkResult` chỉ lưu tham chiếu tới `Thread` để phục vụ kiểm chứng trong bài. Trong code nghiệp vụ thật, kết quả nên là dữ liệu domain, không trả `Thread` cho client.
- `handle.get(5, SECONDS)` đợi nếu chưa hoàn tất rồi trả kết quả, nên năm dòng được in theo thứ tự cố định. Đây là **timeout ở caller khi đọc kết quả**, không phải giới hạn thời gian chạy do BPP tự áp đặt.

Nếu môi trường không giải quyết được dependency, executor bị đóng trước khi nhận task hoặc quá hạn 5 giây, chương trình có thể báo lỗi thay vì in đúng năm dòng. Output trên mô tả trường hợp chạy thành công, không phải cam kết về thời gian scheduler.

### Nếu bỏ `@EnableAsync` thì sao?

Với ứng dụng chỉ có cấu hình tự khai báo như ví dụ và không có cơ chế async khác, Spring sẽ không đăng ký BPP qua `@EnableAsync`; phương thức có annotation đơn thuần là một method Java thường. Caller có thể trực tiếp thực thi thân `process` và nhận `CompletableFuture.completedFuture` đã hoàn tất trên caller. Chỉ nhìn thấy kiểu trả về `CompletableFuture` chưa đủ kết luận đã có xử lý async.

## 6. Những ranh giới của proxy mode

### A. Self-invocation: gọi `this.method()` bỏ qua proxy

Ví dụ minh họa:

```java
@Service
class InvoiceService {
    public CompletableFuture<String> generate() {
        // this nằm ở target object, không đi qua proxy async.
        return sendAsync();
    }

    @Async("invoiceExecutor")
    public CompletableFuture<String> sendAsync() {
        return CompletableFuture.completedFuture("sent");
    }
}
```

Đoạn này là một lớp minh họa trong ứng dụng có bean `invoiceExecutor` và `@EnableAsync`, không phải chương trình độc lập. Gọi `generate()` từ ngoài qua proxy sẽ vào target và target tự gọi `sendAsync()` bằng `this`; **lời gọi nội bộ** không đi qua interceptor, dù `sendAsync` mang `@Async`.

Cách giải quyết thường là tách `sendAsync()` vào một Spring bean khác và inject bean đó, rồi gọi qua bean reference. Cần tránh tự inject proxy vào chính mình chỉ để né self-invocation nếu có thể tổ chức lại ranh giới service rõ ràng hơn.

### B. Object tự `new` không qua BeanPostProcessor

```java
WorkService direct = new WorkService();
direct.process("A");
```

Đoạn trên giả định sử dụng class `WorkService` của ví dụ. Object `direct` được tạo bằng `new` không được `ApplicationContext` xử lý, nên BPP không gắn AOP proxy cho nó. Method chạy trực tiếp trên caller và `@Async` không tác động đến lời gọi. Lấy object qua `context.getBean(...)` hoặc inject Spring bean đúng cách mới cho cơ hội áp dụng proxy.

### C. Proxy loại nào và method nào chặn được?

| Tình huống | Điều cần nhớ |
| --- | --- |
| Bean triển khai interface, mặc định proxy theo interface | JDK dynamic proxy expose interface; client nên inject/call qua interface hợp lệ. |
| Bean không có interface phù hợp hoặc ép `proxyTargetClass=true` | Có thể dùng class-based proxy, yêu cầu class/method đủ điều kiện subclass/override. |
| `private` method | Không thể được gọi bên ngoài qua proxy theo cách annotation AOP mong đợi. |
| `final` method trên class-based proxy | Không thể override để chặn; annotation không biến nó thành async. |
| `final` class cần class-based proxy | Không thể subclass thông thường, có thể gặp lỗi tạo proxy. |
| Constructor, gọi nội bộ trong lifecycle setup hoặc method `@PostConstruct` | Không phải các điểm gọi qua proxy ứng dụng sau khi bean đã sẵn sàng; đừng kỳ vọng annotation tự chuyển sang executor. |
| `@Async` trên phương thức khai báo trong `@Configuration` class | Không phải vị trí sử dụng được Spring khuyến nghị/hỗ trợ. Nên đặt nghiệp vụ async ở service bean. |

`@EnableAsync(proxyTargetClass = true)` buộc class-based proxy ở proxy mode, nhưng cũng có thể ảnh hưởng các bean AOP khác trong cùng context. Thay đổi proxy mode cần cân nhắc tương thích kiểu inject/interface, đặc biệt khi hệ thống đã có `@Transactional`, security hoặc caching.

### D. Scope application context

`@EnableAsync` áp dụng trong context tương ứng. Một root context và một servlet child context có thể có bean scopes/proxy infrastructure riêng. Kiểm tra context thực sự quản lý service, thay vì chỉ thấy annotation được khai báo ở một cấu hình khác.

### E. Thực thi đồng bộ từ một executor đặc biệt

Dù `AopUtils.isAopProxy(service) == true`, việc chạy trên worker khác caller vẫn phụ thuộc executor. Một executor chạy trực tiếp như `Runnable::run` có thể xử lý task ngay trên caller. Với `CallerRunsPolicy`, pool bị bão hòa cũng có thể ép caller tự chạy task. Sự tồn tại của BPP/proxy **không chứng minh** mọi lời gọi đều tạo sự song song thực tế.

## 7. Processor không phải nơi quyết định mọi cấu hình async

### Chọn executor theo method hoặc mặc định

Trong code nghiệp vụ, `@Async("mailExecutor")` và `@Async("reportExecutor")` thường làm rõ pool phục vụ từng loại tải. Interceptor dùng qualifier này khi tìm executor tương ứng. Nếu tên bean không tồn tại, lỗi có thể phát sinh ở lúc invocation.

`AsyncConfigurer` là một giao diện cấu hình được Spring hỗ trợ để cung cấp executor mặc định và `AsyncUncaughtExceptionHandler`. Khi không có qualifier, Spring áp dụng quy tắc tìm executor theo cấu hình hiện hành: ví dụ một bean `TaskExecutor` phù hợp, bean `Executor` tên `taskExecutor`, hoặc fallback theo phiên bản/điều kiện. **Không nên phụ thuộc vào tên thread hay pool mặc định nếu chưa xác nhận bean nào được chọn.**

`AsyncAnnotationBeanPostProcessor` có các điểm cấu hình như `setExecutor(...)`, `setExceptionHandler(...)` và `setAsyncAnnotationType(...)`; chúng dành cho trường hợp tùy biến hạ tầng. Trong ứng dụng thông thường, dùng `@EnableAsync`, cấu hình `AsyncConfigurer` hoặc khai báo executor bean rõ ràng sẽ đơn giản và dễ kiểm soát hơn việc tạo một processor thứ hai thủ công.

### `@EnableAsync` có hỗ trợ annotation khác không?

Theo cấu hình Spring, mặc định có thể nhận `@Async` của Spring, annotation async của Jakarta/EJB khi dependency thích hợp hiện diện, hoặc một loại annotation tùy chỉnh được cấu hình qua thuộc tính `annotation` của `@EnableAsync`. Việc thêm custom annotation chỉ có ích khi bộ advisor thực sự được cấu hình để nhận annotation đó; không phải một cơ chế tùy ý bắt mọi annotation.

Ví dụ cú pháp cấu hình:

```java
@EnableAsync(annotation = MyAsync.class)
@Configuration
class CustomAsyncConfig {
}
```

Đây là **mã cấu hình minh họa**; cần khai báo `@interface MyAsync`, import và các điều kiện runtime phù hợp. Đừng giả định annotation mới tự tương đương hoàn toàn `@Async("executorName")` về cách diễn giải qualifier.

### Thứ tự xử lý với AOP khác

Bean async có thể đồng thời có advice về transaction, cache, authorization, tracing. Theo javadoc, `AsyncAnnotationBeanPostProcessor` được sắp xếp mặc định ở cuối chuỗi BeanPostProcessor để có thể bổ sung async advisor lên proxy đã có; advisor async thường được đặt trước các advisor hiện hữu nhằm chuyển việc sang executor sớm.

Điều đó **không thay thế việc kiểm tra advice order thực tế** khi có nhiều proxy hoặc cấu hình tùy chỉnh. Đặc biệt, một transaction gắn với thread caller **không tự chuyển sang worker**. Với nghiệp vụ cần transaction bên trong task, xác định ranh giới giao dịch tại phía thực thi, lựa chọn proxy/advisor và thiết kế failure handling phù hợp; không chỉ đặt cả `@Transactional` và `@Async` rồi suy ra chắc chắn thứ tự.

## 8. Processor liên quan gì đến kết quả và ngoại lệ?

`AsyncAnnotationBeanPostProcessor` trang bị advisor/proxy **khi khởi tạo bean**; nó không hoàn tất công việc thay cho executor. **Khi method được gọi**, interceptor lựa chọn executor, nộp invocation và xử lý kết quả theo kiểu trả về:

| Loại kết quả/tình huống | Điểm quan sát thực tế |
| --- | --- |
| `CompletableFuture<T>` hoặc `Future<T>` | Handle từ proxy, completion/exception được caller quan sát |
| `@Async void` ném lỗi trong worker | `AsyncUncaughtExceptionHandler`, log/metric |
| Executor không tồn tại hoặc từ chối task | Lỗi ở đường phân giải/submit, có thể trước khi caller nhận Future |
| Caller timeout hoặc cancel | Không tự bảo đảm worker dừng hoặc side effect rollback |

Ví dụ rút gọn về API trong bean service: `@Async("lessonExecutor") public CompletableFuture<String> compute()` có thể trả `CompletableFuture.completedFuture("ok")` **trong worker**; caller nhận handle mà proxy cung cấp. Không suy ra phương thức đã chạy ngay trên caller chỉ vì target tạo completed future. Để học chi tiết `get/join`, `thenCompose`, cancellation hay đường lỗi, xem hợp đồng của các kiểu trả về; mục tiêu ở đây là phân biệt trách nhiệm processor với interceptor và executor.

## 9. So sánh với `ScheduledAnnotationBeanPostProcessor`

Hai lớp có tên tương tự, nhưng cơ chế kích hoạt khác nhau:

| | `AsyncAnnotationBeanPostProcessor` | `ScheduledAnnotationBeanPostProcessor` |
| --- | --- | --- |
| Annotation điển hình | `@Async` | `@Scheduled` |
| Bật theo cơ chế thông thường | `@EnableAsync` | `@EnableScheduling` |
| Mục đích | Gắn interceptor/proxy để chuyển **lời gọi phương thức do caller khởi phát** sang executor. | Phát hiện method theo lịch và **đăng ký tác vụ theo lịch** với scheduler. |
| Khi nào công việc bắt đầu? | Khi một caller gọi qua proxy được áp dụng advisor. | Khi điều kiện lịch fixed rate/fixed delay/cron đến hạn. |
| Có tham số runtime từ caller? | Có, caller gọi method với argument bình thường. | Method scheduled thường được gọi theo lịch, không nhận argument động từ caller theo cách đó. |
| Thành phần thực thi | `Executor`/`TaskExecutor` được chọn. | `TaskScheduler` và cấu hình scheduling phù hợp. |

Vì vậy câu “Spring có BeanPostProcessor nên chắc nó quét và tự chạy mọi method async” là sai. Processor async trang bị **đường chặn lời gọi**, còn scheduler chủ động đăng ký **thời điểm phát sinh công việc**.

## 10. Quy trình chẩn đoán `@Async` không hoạt động

Thực hiện theo thứ tự để xác định lỗi nằm ở đâu:

1. **Bean có do Spring tạo không?** Kiểm tra `ApplicationContext` chứa bean và ứng dụng gọi reference được inject/get từ context; tránh đối tượng tự `new`.
2. **Context đó bật async chưa?** Kiểm tra `@EnableAsync` ở cấu hình áp dụng; trong proxy mode có thể kiểm tra sự hiện diện của bean `AsyncAnnotationBeanPostProcessor`.
3. **Có proxy/advisor không?** Dùng `AopUtils.isAopProxy(bean)` trong proxy mode và xem kiểu proxy. Nếu service có interface/JDK proxy, kiểm tra cách inject theo interface.
4. **Method có thể intercept không?** Kiểm tra `public`, không `final` với class proxy, đúng annotation ở class/method, không gọi qua `this`.
5. **Executor nào thực sự được chọn?** Kiểm tra `@Async("...")`, tên bean, `AsyncConfigurer`, `threadNamePrefix` và loại executor. Coi chừng một direct executor hoặc `CallerRunsPolicy`.
6. **Lời gọi có qua proxy thật không?** Log caller thread ở chỗ gửi, worker thread trong method; so sánh tên/ID. Không dựa duy nhất vào việc method trả `CompletableFuture`.
7. **Có xảy ra rejection hoặc lỗi bên trong task không?** Kiểm tra exception khi submit, `Future` completion, `AsyncUncaughtExceptionHandler`, queue depth và shutdown.
8. **Caller có tự chặn sau submit không?** Nếu gọi `get()`/`join()` ngay, nhìn bên ngoài vẫn có vẻ tuần tự dù method thực sự chạy trên worker.
9. **Có phụ thuộc context từ caller không?** `ThreadLocal`, MDC, security context, request scope và transaction không tự đi theo worker. Dùng propagation có chủ đích và cleanup trong `finally`.
10. **Có nhiều context/auto-proxy creators không?** Kiểm tra thứ tự AOP, proxy chain, giao dịch và bean lifecycle trong context thực tế.

Một phép kiểm tra tốt phải trả lời ba câu riêng: **processor đã đăng ký chưa, service có proxy chưa và method đang thực thi trên executor nào**. Chỉ một trong ba điều đúng chưa đủ kết luận mọi đường gọi đang async đúng.

## 11. Các lỗi hiểu sai thường gặp

| Nhận định sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Đặt `@Async` là JVM tự mở thread.” | Annotation không có runtime interceptor khi thiếu cấu hình/bean phù hợp. | Bật `@EnableAsync` và gọi Spring-managed bean qua proxy. |
| “`AsyncAnnotationBeanPostProcessor` là thread pool.” | Nó bổ sung AOP advisor/proxy, còn executor mới nhận task. | Phân biệt initialization và invocation. |
| “Có `@EnableAsync` thì mọi method đều bất đồng bộ.” | Chỉ các lời gọi phù hợp pointcut và qua interception mới được xử lý. | Kiểm tra annotation và proxy boundary. |
| “Processor chạy method async khi bean được tạo.” | Bean post-processing chỉ xây infrastructure. | Task chạy khi caller gọi qua proxy. |
| “Self-invocation sẽ tự chuyển worker.” | `this` gọi trực tiếp target, không qua proxy trong mode mặc định. | Tách method sang bean khác hoặc thiết kế ranh giới AOP phù hợp. |
| “Object `new` có `@Async` vẫn async.” | Không có post-processing của Spring cho object ấy. | Lấy bean qua context/injection. |
| “BPP đã đăng ký thì chắc mọi lời gọi chạy thread khác.” | Executor trực tiếp hoặc CallerRuns có thể dùng caller. | Kiểm tra delegate, overload, log thread và kết quả. |
| “`CompletableFuture` chắc chắn là async.” | Có thể là `completedFuture` được tạo ngay trên caller. | Quan sát proxy/executor thay vì suy từ return type. |
| “`@Async` giữ transaction từ request thread.” | Transaction context thường gắn thread. | Thiết kế transaction trong worker, kiểm tra advice order. |
| “`@Scheduled` và `@Async` cùng một processor.” | Scheduler và async advisor có processor và cơ chế khác nhau. | Phân biệt `ScheduledAnnotationBeanPostProcessor` và async BPP. |
| “Dùng `@Async void` sẽ báo exception tại dòng gọi.” | Lỗi xảy ra ở worker, caller không có future. | Cấu hình uncaught exception handler hoặc trả completion handle. |
| “Thêm nhiều processor thủ công sẽ giúp chạy nhanh hơn.” | Có thể làm proxy/advisor trùng, khó kiểm soát infrastructure. | Dùng một cấu hình `@EnableAsync` chuẩn và executor sizing đúng. |

## 12. Bài tập tự kiểm tra

**Câu 1.** Trong proxy mode, ai chịu trách nhiệm nhận diện `@Async` trên bean và gắn advice tương ứng?

**Đáp án:** `AsyncAnnotationBeanPostProcessor` áp dụng `AsyncAnnotationAdvisor` vào proxy của bean phù hợp. Executor chỉ được sử dụng khi có lời gọi bị interceptor xử lý.

**Câu 2.** Vì sao một bean có `@Async` nhưng method vẫn chạy trên caller khi tạo bằng `new`?

**Đáp án:** Object không được IoC container post-process, không có AOP proxy, nên annotation không tạo hiệu ứng đối với lời gọi Java trực tiếp.

**Câu 3.** `@EnableAsync` làm gì, và nó có bắt đầu chạy tất cả các phương thức `@Async` lúc startup không?

**Đáp án:** Nó đăng ký hạ tầng async cho context. Processor chuẩn bị proxy/advisor; method chỉ thực thi khi được gọi qua đường interception sau đó.

**Câu 4.** `this.sendAsync()` bên trong service có proxy có chạy qua async advice không?

**Đáp án:** Trong proxy mode mặc định, không. Đây là self-invocation trên target; cần gọi qua Spring proxy từ bean khác hoặc cơ chế interception phù hợp.

**Câu 5.** Một service được AOP proxy và `@Async("lessonExecutor")`, nhưng task vẫn chạy ngay trên caller. BPP có chắc lỗi không?

**Đáp án:** Chưa chắc. Delegate executor có thể thực thi trực tiếp, hoặc saturation policy `CallerRunsPolicy` chuyển việc sang caller. Phải kiểm tra executor và đường invocation.

**Câu 6.** Vì sao trong ví dụ có thể nhận cả `processorRegistered=true` và `serviceProxied=true`?

**Đáp án:** `@EnableAsync` đăng ký processor, rồi processor tạo/bổ sung AOP proxy cho `WorkService` có method `@Async`. Hai giá trị kiểm tra hai giai đoạn khác nhau.

**Câu 7.** Có thể lấy exception ném từ `@Async void` bằng `Future.get()` không?

**Đáp án:** Không, vì method `void` không trả handle. Cần `AsyncUncaughtExceptionHandler` hoặc thay hợp đồng method thành `CompletableFuture<T>` khi muốn caller theo dõi kết quả.

**Câu 8.** Một ứng dụng chọn `@EnableAsync(mode = AdviceMode.ASPECTJ)`. `AopUtils.isAopProxy(service)` trả `false` có đủ kết luận async chưa bật không?

**Đáp án:** Không. AspectJ weaving không dựa trên AOP proxy tương tự proxy mode; cần kiểm tra weaving, dependency và hành vi thực tế.

**Câu 9.** Annotation `@Scheduled` trên bean có được chính `AsyncAnnotationBeanPostProcessor` lập lịch không?

**Đáp án:** Không. Lập lịch có hạ tầng riêng, điển hình là `ScheduledAnnotationBeanPostProcessor` và `TaskScheduler`.

### Ghi nhớ

Hãy lần theo **cấu hình → bean post-processing → AOP proxy/advisor → method invocation → executor → completion**. `AsyncAnnotationBeanPostProcessor` thuộc phần **tạo đường chặn lời gọi cho Spring bean**; async interceptor xử lý lời gọi và giao công việc cho executor. Khi debug, xác minh từng mắt xích thay vì suy luận rằng chỉ cần có annotation là task chắc chắn chạy song song.

### Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): bật `@EnableAsync`, proxy mode, `@Async` và executor.
- [Spring Framework — AsyncAnnotationBeanPostProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/AsyncAnnotationBeanPostProcessor.html): processor, advisor, annotation và exception handler.
- [Spring Framework — EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): cách bật, scope theo context, proxy/AspectJ và thứ tự.
- [Spring Framework — AsyncAnnotationAdvisor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/AsyncAnnotationAdvisor.html): pointcut/advice cho async method.
- [Spring Framework — AnnotationAsyncExecutionInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/AnnotationAsyncExecutionInterceptor.html): chọn executor theo annotation và giao lời gọi.
