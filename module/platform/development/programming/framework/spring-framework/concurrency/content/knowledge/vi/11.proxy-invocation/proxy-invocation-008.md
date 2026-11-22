# Giới hạn khởi tạo sớm khi dùng AsyncConfigurer trong Spring

Khi bật xử lý bất đồng bộ bằng `@EnableAsync`, Spring cho phép tùy biến executor mặc định và cách xử lý exception của phương thức `@Async void` qua interface **`AsyncConfigurer`**. Đây là một cơ chế hữu ích, nhưng có một giới hạn vòng đời dễ bị bỏ qua: **configuration class triển khai `AsyncConfigurer` được Spring khởi tạo sớm trong giai đoạn bootstrap của ApplicationContext**.

Điều này ảnh hưởng trực tiếp đến việc tiêm dependency và proxy. Nếu class `AsyncConfigurer` yêu cầu tạo một service khác quá sớm, service đó có thể chưa đi qua đủ các `BeanPostProcessor`, bao gồm các bộ xử lý tạo proxy cho các annotation nhất định. Kết quả có thể là bean được khởi tạo không đúng thời điểm, vòng phụ thuộc, thiếu một số advice hoặc hành vi không như kỳ vọng. Spring khuyên **để các dependency đó lazy tối đa có thể**.

Bài học thuộc nhóm **Proxy và lời gọi** của module **Spring Framework – concurrency**. Trọng tâm là hiểu giới hạn trên, phân biệt nó với việc `@Async` không hoạt động do self-invocation, và tổ chức cấu hình executor sao cho **đúng bean, đúng lifecycle, đúng proxy**.

## 1. `AsyncConfigurer` dùng để làm gì?

Spring `@EnableAsync` kích hoạt xử lý phương thức đánh dấu `@Async`. Với phương thức gọi **qua proxy** trong chế độ mặc định, Spring chọn executor để chuyển phần thực thi sang một thread khác. `AsyncConfigurer` là hook cấp cấu hình cho hai vấn đề:

```java
public interface AsyncConfigurer {
    default Executor getAsyncExecutor() {
        return null;
    }

    default AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return null;
    }
}
```

Đây là **hình dạng API rút gọn để giải thích**; không nên sao chép interface này vào dự án vì Spring đã cung cấp `org.springframework.scheduling.annotation.AsyncConfigurer`. Các phương thức thực tế là phương thức mặc định và có thể trả null khi không cần tùy biến mục tương ứng.

- `getAsyncExecutor()`: cung cấp **executor mặc định** cho những lời gọi `@Async` không chọn executor cụ thể.
- `getAsyncUncaughtExceptionHandler()`: xử lý các exception không thể gửi trực tiếp về caller từ phương thức `@Async` có kiểu trả về `void`.
- Nếu `@Async("reportExecutor")` chọn một executor có tên/qualifier cụ thể, cấu hình chọn tên ấy được xét cho lời gọi; không nên cho rằng mọi `@Async` đều dùng executor mặc định của `AsyncConfigurer`.
- Nếu dùng `Future<T>` hoặc `CompletableFuture<T>`, caller cần quan sát completion/exception qua Future. Exception handler cho `void` không thay thế đường báo lỗi của Future.

Để tùy biến:

```java
@Configuration
@EnableAsync
public class AsyncConfig implements AsyncConfigurer {
    @Override
    public Executor getAsyncExecutor() {
        // Trả về executor mặc định đã cấu hình.
    }

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        // Trả về handler cho @Async void khi cần.
    }
}
```

Đây là **fragment ý tưởng, không phải chương trình biên dịch độc lập**: phần body và imports chưa được viết. Phần sau sẽ có chương trình Spring Boot đầy đủ và các cấu hình thay thế hoàn chỉnh.

## 2. “Khởi tạo sớm” nghĩa là gì?

Trong tiến trình tạo `ApplicationContext`, Spring phải đăng ký các thành phần infrastructure để nhận diện `@Async`, quyết định cách áp advice/proxy và cấu hình executor/exception handler. Chính vì vậy, **các configuration class triển khai `AsyncConfigurer` được khởi tạo sớm**, thay vì được giả định chỉ khởi tạo ở cuối bootstrap.

Một timeline giản lược:

```text
Khởi động ApplicationContext
       |
       v
Đọc @Configuration / @EnableAsync
       |
       v
Đăng ký async infrastructure và các BeanPostProcessor liên quan
       |
       +--> Cần phát hiện AsyncConfigurer
       |       |
       |       v
       |    AsyncConfigurer có thể được khởi tạo SỚM
       |       |
       |       +--> Nếu eager inject service khác:
       |               service đó có thể bị tạo quá sớm
       |               so với một số post-processor/proxy
       |
       v
Hoàn tất đăng ký/áp dụng các hậu xử lý cho bean bình thường
       |
       v
Các singleton sẵn sàng / context bắt đầu phục vụ
```

Hình trên **không phải thứ tự mọi callback cố định giữa tất cả phiên bản Spring**. Nó minh họa **nguyên nhân cơ chế**: khi một infrastructure component đòi truy cập `AsyncConfigurer` từ sớm, các dependency bị kéo theo có thể chưa trải qua điều kiện xử lý bình thường của ứng dụng.

### 2.1. Cảnh báo chính thức của Spring

Javadoc của `@EnableAsync` lưu ý rằng configuration class triển khai `AsyncConfigurer` **khởi tạo sớm khi bootstrap**; nếu cần phụ thuộc vào các bean khác, nên **khai báo chúng lazy nhiều nhất có thể**, để chúng có cơ hội đi qua các post-processor khác.

Điều này có hai hệ quả:

1. **Không giả định** mọi dependency đang được inject vào `AsyncConfigurer` đã có đầy đủ proxy/advice giống như khi được resolve muộn ở runtime.
2. **Không tạo dây chuyền dependency phức tạp** bên trong configurer chỉ để lựa chọn một executor; ưu tiên cấu hình đơn giản, tách bean rõ ràng và trì hoãn resolve khi cần.

Nguồn chính: Javadoc Spring Framework 6.2 `EnableAsync` (phần chú ý về `AsyncConfigurer`): https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html

### 2.2. Vì sao post-processor lại quan trọng?

Spring dùng các `BeanPostProcessor` và infrastructure AOP để can thiệp quá trình tạo bean, có thể bọc bean bằng proxy trước khi đưa vào sử dụng. Tùy cấu hình, proxy/advice có thể xử lý `@Async`, `@Transactional`, caching, security hoặc các cross-cutting concerns khác.

Ví dụ một service có `@Transactional` cần được gọi **qua proxy chứa transaction interceptor** thì annotation mới có tác dụng trong chế độ proxy thông thường. Nếu service được khởi tạo/tiếp cận quá sớm rồi một tham chiếu chưa được xử lý đầy đủ bị giữ lại, bạn có thể thấy lời gọi không có behavior như mong đợi.

Cần diễn đạt thận trọng:

- **Không phải cứ tiêm service vào `AsyncConfigurer` thì chắc chắn mất proxy.** Tác động phụ thuộc thời điểm và chuỗi khởi tạo thực tế.
- **Không phải `@Transactional` hay `@Async` luôn mất tác dụng** nếu class configurer được tạo sớm. Đây là **rủi ro phụ thuộc lifecycle** cần tránh và kiểm chứng.
- Vấn đề chính là **lấy/khởi tạo dependency quá sớm**, không phải bản thân từ khóa `@Configuration` hay interface `AsyncConfigurer` luôn lỗi.

## 3. Ví dụ cấu hình có rủi ro: tiêm eager service vào AsyncConfigurer

Đoạn sau minh họa **mẫu nên tránh**:

```java
@Configuration
@EnableAsync
public class RiskyAsyncConfig implements AsyncConfigurer {
    private final BillingService billingService;

    public RiskyAsyncConfig(BillingService billingService) {
        this.billingService = billingService; // Eager dependency
    }

    @Override
    public Executor getAsyncExecutor() {
        billingService.auditBootstrap(); // Gọi business logic lúc cấu hình!
        return Executors.newFixedThreadPool(4);
    }
}
```

Đây là **fragment giải thích rủi ro**, không phải chương trình hoàn chỉnh: `BillingService` do ứng dụng định nghĩa, imports và shutdown policy chưa được cung cấp. **Không dùng đoạn mã trên như một giải pháp production.**

Các vấn đề độc lập:

1. Constructor của `RiskyAsyncConfig` yêu cầu `BillingService` ngay lúc configurer được tạo. Nếu Spring đang ở pha bootstrap sớm, dependency có thể bị kéo vào quá trình tạo bean trước thời điểm thích hợp.
2. Nếu `BillingService` cần AOP proxy (ví dụ `@Transactional` hoặc `@Async`), việc bị resolve sớm có thể dẫn tới hành vi proxy không đúng kỳ vọng hoặc thông báo bean chưa đủ điều kiện đi qua toàn bộ post-processor.
3. Gọi `billingService.auditBootstrap()` bên trong `getAsyncExecutor()` trộn **khởi tạo infrastructure** với **nghiệp vụ**, dễ gây side effect, truy cập DB ngoài thời điểm cho phép hoặc khởi động task trước khi context sẵn sàng.
4. `Executors.newFixedThreadPool(4)` là executor JDK mới tạo, không tự là Spring bean và không tự được Spring đóng theo lifecycle bean nếu không có quản lý bổ sung.
5. Nếu dependency lại cần chính executor/`@Async` infrastructure đang thiết lập, có thể phát sinh vòng phụ thuộc: configurer → service → executor/proxy → configurer.

**Triệu chứng có thể gặp** (không phải triệu chứng luôn xảy ra): lỗi bean đang được tạo, BeanCurrentlyInCreationException, startup thất bại, log báo bean “not eligible for getting processed by all BeanPostProcessors”, proxy không xuất hiện đúng lúc, hoặc startup có side effect bất thường.

Đừng kết luận nguyên nhân chỉ từ một log. Cần nhìn **dependency graph**, thời điểm resolve và thực tế bean được proxy hay chưa.

## 4. Cách ưu tiên: không dùng AsyncConfigurer nếu chỉ muốn chọn một executor cụ thể

Trong nhiều dự án, mục tiêu chỉ là “dùng thread pool A cho báo cáo, thread pool B cho email”. Không nhất thiết triển khai `AsyncConfigurer`. Có thể:

1. Tạo một bean `ThreadPoolTaskExecutor` được Spring quản lý.
2. Bật `@EnableAsync`.
3. Dùng `@Async("beanName")` trên method cần dùng pool đó.
4. Gọi method qua một Spring bean khác để đi qua proxy.

Mô hình:

```text
@Configuration @EnableAsync
          |
          +-- @Bean("reportExecutor") --> ThreadPoolTaskExecutor (managed)
          |
Controller bean --> ReportService proxy --> @Async("reportExecutor")
                                               |
                                               v
                                         Worker threads
```

Cách này giảm số lý do phải dùng `AsyncConfigurer`, tránh phụ thuộc business service trong hook infrastructure, đồng thời tường minh executor nào được chọn.

### 4.1. Chương trình Spring Boot hoàn chỉnh cho môi trường Spring Boot 3.x

Dùng **Java 17+**, **Spring Boot 3.x / Spring Framework 6.x** và dependency `spring-boot-starter-web`. Đặt mã vào **src/main/java/com/example/demo/AsyncStartupApplication.java**. Đây là ứng dụng Boot hoàn chỉnh về cấu trúc class, cần được biên dịch/chạy trong **project Spring Boot có dependencies tương ứng**; không thể chạy bằng `javac` trần khi thiếu Spring jars.

```java
package com.example.demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
public class AsyncStartupApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncStartupApplication.class, args);
    }

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(20);
        pool.setThreadNamePrefix("report-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return pool;  // Spring quản lý initialize/shutdown của bean
    }
}

@Service
class ReportService {
    @Async("reportExecutor")
    public CompletableFuture<String> build(String reportId) {
        String worker = Thread.currentThread().getName();
        if (!worker.startsWith("report-")) {
            throw new IllegalStateException("Unexpected executor: " + worker);
        }
        return CompletableFuture.completedFuture("built:" + reportId);
    }
}

@RestController
class ReportController {
    private final ReportService reports;

    ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/reports/{id}/build")
    public CompletableFuture<String> build(@PathVariable String id) {
        return reports.build(id);
    }
}
```

Trong một dự án có Gradle wrapper và Spring Boot Gradle plugin, chạy:

```bash
./gradlew bootRun
curl -s http://localhost:8080/reports/R1/build
```

Trên Windows, dùng `gradlew.bat bootRun`. Khi request được nhận và method chạy thành công, response body là:

```text
built:R1
```

Giải thích:

- `@EnableAsync` được đặt trên application class để bật async infrastructure.
- `@Bean("reportExecutor")` tạo **bean executor có tên**, không cần `AsyncConfigurer`.
- `ReportController` gọi **bean `ReportService` khác**, nên lời gọi đi qua proxy `@Async` trong chế độ mặc định.
- `@Async("reportExecutor")` chọn bean tường minh; tên thread bắt đầu bằng `report-` là một cách kiểm tra minh họa.
- Spring MVC có thể xử lý response kiểu `CompletableFuture` bằng cơ chế async request; **HTTP client vẫn chờ Future hoàn thành để nhận body**, không phải ngay khi vừa submit.
- Method `build` ở đây chỉ trả chuỗi để minh họa execution path, **không tạo báo cáo thực**. Nếu cần xử lý job dài và trả 202 ngay, phải có giao thức job ID/status riêng.

**Lợi ích về bootstrap:** không có `AsyncConfigurer` giữ tham chiếu đến service nghiệp vụ hoặc bắt nó khởi tạo khi Spring còn đang cấu hình async infrastructure.

### 4.2. Nếu cần executor mặc định mà không chỉ rõ mỗi @Async?

Javadoc `@EnableAsync` mô tả việc Spring tìm một `TaskExecutor` duy nhất hoặc `Executor` có tên `taskExecutor`, nếu không có cấu hình custom khác. Vì vậy có thể dùng một bean executor được đặt tên và bảo đảm không mơ hồ. Trong dự án Spring Boot, **auto-configuration và số lượng executor bean có thể ảnh hưởng lựa chọn thực tế**; không nên suy luận default chỉ dựa vào tên class.

Để có kết quả dễ hiểu, nếu cần chạy trên một pool cụ thể thì `@Async("reportExecutor")` vẫn là lựa chọn tường minh. Khi muốn thay đổi executor mặc định cho toàn bộ `@Async` không qualifier, `AsyncConfigurer` là một tùy chọn, nhưng cần xử lý đúng vấn đề khởi tạo sớm.

## 5. Nếu phải dùng AsyncConfigurer: trì hoãn dependency một cách có chủ đích

Có những trường hợp thực sự cần `getAsyncExecutor()` làm mặc định hoặc tùy biến `getAsyncUncaughtExceptionHandler()` tập trung. Khi đó cần **đơn giản hóa graph của configurer**, và tránh eagerly lấy các bean có thể cần đi qua post-processor.

### 5.1. Dùng @Lazy tại điểm inject

Một phương án là inject dependency qua **lazy-resolution proxy** thay vì lấy target thật ngay tại constructor của `AsyncConfigurer`.

Ví dụ **cấu hình thay thế**, không dùng đồng thời với application class ở mục 4 trong cùng project nếu không chủ ý phối hợp các cấu hình async:

```java
package com.example.demo;

import java.util.concurrent.Executor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class LazyAsyncConfig implements AsyncConfigurer {
    private final Executor defaultExecutor;

    public LazyAsyncConfig(
            @Lazy @Qualifier("reportExecutor") Executor defaultExecutor) {
        this.defaultExecutor = defaultExecutor;
    }

    @Override
    public Executor getAsyncExecutor() {
        return defaultExecutor;
    }
}
```

Đoạn này là **class cấu hình đầy đủ** nhưng phụ thuộc vào một bean `reportExecutor` đã được khai báo riêng (chẳng hạn bean ở mục 4) và những import/dependency Spring có sẵn. `@Lazy` trên **injection point** nói với Spring cung cấp một proxy trì hoãn resolve dependency đích. Việc trả proxy từ `getAsyncExecutor()` không nhất thiết buộc target executor khởi tạo ngay khi configurer được tạo.

**Giới hạn cần nắm:**

- `@Lazy` tại injection point **không biến toàn bộ ApplicationContext thành lazy**. Nếu bean đích được một singleton khác eager inject, nó vẫn có thể bị tạo lúc startup.
- Lazy proxy trì hoãn **lần truy cập thực sự vào target**; nếu constructor, `@PostConstruct` hoặc `getAsyncExecutor()` trực tiếp gọi method trên proxy quá sớm, target vẫn có thể bị resolve quá sớm.
- `@Lazy` không sửa được một **dependency cycle thực sự** hay logic nghiệp vụ đang tự kích hoạt lúc startup.
- Nếu bean không tồn tại, proxy lazy có thể được inject nhưng lỗi chỉ bộc lộ **khi thực sự truy cập**. Cần startup validation/test phù hợp.
- Mục tiêu là giảm khả năng tạo dependency trước khi hệ thống post-processor sẵn sàng, không phải lời hứa tuyệt đối rằng mọi cấu hình sẽ luôn an toàn.

### 5.2. ObjectProvider để trì hoãn việc resolve

`ObjectProvider<T>` giúp mang một **handle tra cứu** thay vì bắt container lấy target ngay khi constructor chạy:

```java
package com.example.demo;

import java.util.concurrent.Executor;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class ProviderAsyncConfig implements AsyncConfigurer {
    private final ObjectProvider<Executor> executors;

    public ProviderAsyncConfig(
            @Qualifier("reportExecutor") ObjectProvider<Executor> executors) {
        this.executors = executors;
    }

    @Override
    public Executor getAsyncExecutor() {
        return executors.getObject();
    }
}
```

Đây cũng là **phương án cấu hình thay thế** chỉ dành cho dự án đã khai báo bean `reportExecutor`; không kích hoạt đồng thời nhiều class `AsyncConfigurer` nếu không có chủ đích. Trong cấu hình trên:

- Constructor chỉ nhận provider; không trực tiếp gọi `getObject()` tại đó.
- Khi `getAsyncExecutor()` được gọi, `getObject()` mới yêu cầu bean thực; điều này **dời thời điểm resolve** so với eager constructor injection.
- **Không giả định thời điểm `getAsyncExecutor()` luôn là “sau khi tất cả post-processor hoàn tất”** trong mọi phiên bản/tình huống. Nếu framework hoặc code khác gọi hook từ sớm, provider cũng sẽ resolve sớm.
- Provider hữu ích khi muốn xử lý optional/lazy resolution rõ ràng; tuy nhiên nếu chỉ cần định tuyến method cụ thể, bean executor riêng cộng `@Async("reportExecutor")` thường đơn giản và ít coupling hơn.

**So sánh nhanh hai cách:**

| Cách | Target được lấy lúc nào? | Điều cần chú ý |
| --- | --- | --- |
| Inject `Executor` trực tiếp | Eager khi tạo configurer nếu không lazy | Có thể kéo theo khởi tạo sớm |
| `@Lazy` tại điểm inject | Proxy trước, target lúc lần đầu dùng | Dùng proxy quá sớm vẫn tạo target sớm |
| Inject `ObjectProvider<Executor>` | Provider trước; target lúc gọi `getObject()` | Đừng gọi `getObject()` trong constructor |
| Bean executor riêng + `@Async("name")` | Container quản lý bean và chọn bằng qualifier | Thường không cần AsyncConfigurer |

### 5.3. Vì sao chỉ đặt @Lazy trên class service có thể chưa đủ?

Trong Spring, một **bean definition lazy** thường chỉ được tạo khi có yêu cầu. Nhưng nếu một singleton **không lazy** cần dependency đó để hoàn tất constructor, Spring phải tạo dependency để thỏa quan hệ inject. Do vậy:

```java
@Lazy
@Service
class ExpensiveService {
    // Không bảo đảm được trì hoãn nếu singleton eager khác yêu cầu ngay.
}
```

Chỉ đặt `@Lazy` trên bean class không giải quyết mọi eager dependency chain. Ngược lại, `@Lazy` tại **constructor parameter** có thể tạo proxy tại injection point và tách việc nhận tham chiếu khỏi việc tạo target. Tuy nhiên, **dùng proxy sớm sẽ lại kích hoạt target**.

Tài liệu: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html

## 6. Java 17+ runnable: hình dung “giữ tham chiếu quá sớm” và “tra cứu muộn”

Ví dụ thuần Java sau không dùng Spring, nhưng mô phỏng đúng **mối nguy khi chụp tham chiếu trước khi object được bọc/decorate**. Nó không phải tái hiện chính xác Spring `BeanPostProcessor`; nó chỉ tách biệt cách lấy tham chiếu.

Lưu toàn bộ thành **EarlyReferenceDemo.java**:

```java
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;

public class EarlyReferenceDemo {
    interface Worker {
        String work();
    }

    static final class RawWorker implements Worker {
        @Override
        public String work() {
            return "work";
        }
    }

    static Worker addAdvice(Worker target) {
        return () -> "advised(" + target.work() + ")";
    }

    public static void main(String[] args) {
        Worker raw = new RawWorker();

        // Eager: giữ tham chiếu trước khi wrapping.
        Worker capturedTooEarly = raw;

        // Một bước mô phỏng post-processing.
        AtomicReference<Worker> registry =
                new AtomicReference<>(addAdvice(raw));

        // Lazy: chỉ tra cứu ở thời điểm sử dụng.
        Supplier<Worker> lazyLookup = registry::get;

        System.out.println("early=" + capturedTooEarly.work());
        System.out.println("lazy=" + lazyLookup.get().work());
    }
}
```

Biên dịch/chạy:

```bash
javac EarlyReferenceDemo.java
java EarlyReferenceDemo
```

**Stdout xác định:**

```text
early=work
lazy=advised(work)
```

**Phân tích:**

- `capturedTooEarly` nắm đúng `RawWorker`; việc sau đó đưa wrapper mới vào registry **không thay** tham chiếu cũ.
- `lazyLookup` tra cứu ở thời điểm dùng, lấy wrapper được ghi vào registry và thấy hành vi `advised(...)`.
- `AtomicReference` ở đây là nơi giữ tham chiếu registry trong demo; Java có cơ chế visibility phù hợp cho thao tác `set/get`. Nhưng chương trình chạy một thread, không nhằm chứng minh thuật toán concurrent.
- Đây là **ẩn dụ kỹ thuật**, không đồng nhất `ObjectProvider` của Spring với `AtomicReference` và cũng không nói Spring luôn sẽ tạo “raw bean” như demo. Spring quản lý nhiều bước lifecycle và proxy phức tạp hơn.
- Bài học thực tiễn: **đừng bắt configuration class sớm giữ một dependency trước khi cơ chế bọc/hậu xử lý có thể áp dụng**.

## 7. Phân biệt ba thời điểm: tạo configurer, lấy executor và chạy @Async

Trong thực tế, ba hành động có thể nằm ở các giai đoạn khác nhau:

1. **Spring tạo instance `AsyncConfigurer`** để đọc cấu hình async infrastructure.
2. **Hook `getAsyncExecutor()` cung cấp executor** được sử dụng như default; lần resolve executor có thể bị dời lại tùy cấu hình.
3. **Caller gọi một method `@Async` qua proxy**, interceptor chọn executor và giao một task.

Sơ đồ:

```text
BOOTSTRAP
  @EnableAsync
       |
       +-- Tạo AsyncConfigurer (có thể rất sớm)
       |        |
       |        +-- eager service injection: có thể kéo service lên sớm
       |        +-- @Lazy/ObjectProvider: giảm coupling tới thời điểm tạo target
       |
       +-- Thiết lập async proxy infrastructure
       |
RUNTIME
  Bean A --> proxy Bean B --> @Async method --> executor --> worker
```

**Khởi tạo sớm của `AsyncConfigurer` không đồng nghĩa method `@Async` sẽ chạy đồng bộ.** Ngược lại, một phương thức chạy đồng bộ dù đã cấu hình pool đúng có thể do **self-invocation** hoặc không đi qua Spring proxy. Đây là **hai vấn đề khác nhau**.

## 8. Proxy và self-invocation: vấn đề riêng dễ bị chẩn đoán nhầm

Với `@EnableAsync` mặc định (proxy mode), chỉ lời gọi **đi qua Spring proxy** mới bị interceptor xử lý. Ví dụ:

```java
@Service
public class ExampleService {
    public void outer() {
        inner(); // Gọi nội bộ cùng instance, không đi qua proxy.
    }

    @Async("reportExecutor")
    public void inner() {
        System.out.println(Thread.currentThread().getName());
    }
}
```

Đây là fragment; cần bean executor và `@EnableAsync` trong application. Nếu gọi `outer()` qua proxy và nó tiếp tục gọi `inner()` bằng `this`, lời gọi nội bộ **không được `@Async` interceptor chặn** trong proxy mode. Điều này **không phải** triệu chứng đủ để kết luận `AsyncConfigurer` được tạo quá sớm.

### Cách kiểm tra tách bạch

- Gọi `@Async` từ **một bean khác**, không phải `this.method()`.
- Kiểm tra bean đang được gọi có phải **Spring-managed bean** không; đừng dùng `new Service()` rồi kỳ vọng proxy.
- Kiểm tra tên/qualifier executor, thread name prefix và hành vi khi submit.
- Nếu nghi ngờ khởi tạo sớm, kiểm tra dependency graph, vòng phụ thuộc, thời điểm bean bị tạo và danh sách proxy/advisor.
- Nếu nghi ngờ self-invocation, tách method sang một Spring bean chuyên biệt hoặc dùng chiến lược interception khác có chủ ý; **không kỳ vọng `@Lazy` tự sửa self-invocation**.

Javadoc `EnableAsync` nhấn mạnh `AdviceMode.PROXY` chỉ intercept lời gọi đi qua proxy; với `AdviceMode.ASPECTJ` có cơ chế weaving khác và yêu cầu cấu hình phụ thuộc riêng. Không đổi sang AspectJ chỉ để che lỗi dependency graph khi chưa hiểu tác động.

## 9. Executor do Spring quản lý khác executor tự tạo trong getAsyncExecutor

Một ví dụ chính thức của `@EnableAsync` có hình dạng:

```java
@Override
public Executor getAsyncExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("custom-");
    executor.initialize();
    return executor;
}
```

Đây là fragment minh họa cho **cách tự tạo executor bên trong hook**. Khi chỉ `new` và return từ method này mà **không khai báo thành bean do Spring quản lý**, executor **không tự có đầy đủ lifecycle bean**. Vì vậy cần chú ý:

- `initialize()` thủ công khi dùng executor kiểu Spring ngoài quy trình `@Bean`.
- Shutdown/resource cleanup do code ứng dụng chịu trách nhiệm nếu executor không được quản lý như một Spring bean.
- Nếu Spring quản lý executor qua `@Bean` thông thường, container sẽ đảm nhiệm initialization và lifecycle phù hợp; không cần gọi `initialize()` thủ công.
- Tài liệu `EnableAsync` cho biết có thể chú thích `@Bean` trên chính `getAsyncExecutor()` để biến executor trả về thành bean được quản lý. Đây là lựa chọn hợp lệ theo Javadoc, nhưng vẫn cần hiểu dependency và thời điểm configurer khởi tạo.
- Có thể đơn giản hơn khi khai báo `@Bean("reportExecutor")` trong một configuration class **không** triển khai `AsyncConfigurer` rồi tham chiếu bằng `@Async("reportExecutor")`.

### Không gọi phương thức @Bean như factory thông thường một cách vô ý

Đoạn sau dễ gây rối nếu bạn không hiểu `@Configuration(proxyBeanMethods = false)`:

```java
@Configuration(proxyBeanMethods = false)
class ExecutorConfig {
    @Bean
    ThreadPoolTaskExecutor reportExecutor() {
        return new ThreadPoolTaskExecutor();
    }

    ThreadPoolTaskExecutor anotherReference() {
        return reportExecutor(); // Lời gọi Java trực tiếp, tạo instance mới.
    }
}
```

Đây là **fragment giải thích**: nếu proxyBeanMethods=false, tự gọi method `reportExecutor()` như một method Java thông thường sẽ chạy body và tạo object mới, **không phải lấy bean do container đã quản lý**. Nếu cần bean, hãy **inject bean** bằng constructor/qualifier hoặc provider phù hợp. Với cấu hình full `@Configuration` có inter-bean proxy, hành vi khác, nhưng phụ thuộc kiểu proxy config không đáng dùng làm giải pháp mơ hồ cho vấn đề early initialization.

Đừng trả một executor mới chưa initialize ở mỗi lượt gọi hook hoặc tạo nhiều pool ngoài kiểm soát chỉ vì thiếu phương thức lấy bean đúng cách.

## 10. Exception handler không nên kéo service phức tạp vào bootstrap

`getAsyncUncaughtExceptionHandler()` xử lý exception từ phương thức `@Async` có return type `void`. Đây cũng là một hook trong `AsyncConfigurer`. Nếu handler được xây dựng bằng cách eager inject một service logging/metrics phức tạp ngay vào constructor configurer, bạn vẫn có nguy cơ kéo dependency graph lên sớm.

Một cấu hình đơn giản có thể trả handler không phụ thuộc bean nghiệp vụ:

```java
@Override
public AsyncUncaughtExceptionHandler
        getAsyncUncaughtExceptionHandler() {
    return (exception, method, params) -> {
        System.err.println(
                "Async void error in " + method.getName()
                + ": " + exception.getClass().getSimpleName());
    };
}
```

Đây là **fragment method** để đặt trong một class `AsyncConfigurer`, cần import `org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler`. Ví dụ dùng `System.err` cho dễ hiểu; production nên dùng logger/metrics thích hợp, tránh ghi thông tin nhạy cảm.

Nếu cần chuyển lỗi vào một service quan sát khác, có thể:

- Dùng một provider/lazy reference và chỉ resolve khi **handler thực sự được gọi**, không gọi trong constructor.
- Tránh tạo vòng dependency giữa exception handler, executor và chính async infrastructure.
- Ưu tiên phương thức trả `CompletableFuture<T>` khi caller cần kết quả hoặc xử lý exception. `AsyncUncaughtExceptionHandler` chỉ có vai trò riêng với `void`, không thay thế `Future.get()`/`whenComplete()`.

## 11. Vòng phụ thuộc và vì sao @Lazy không phải cách sửa mọi thứ

Một đồ thị có vấn đề có thể trông như sau:

```text
AsyncConfigurer
     |
     | eager requires
     v
AuditService (@Async / @Transactional)
     |
     | requires
     v
Executor or another configuration bean
     |
     +--------------------> AsyncConfigurer infrastructure
```

Vòng như vậy có thể dẫn tới `BeanCurrentlyInCreationException` hoặc trạng thái bootstrap khó suy luận. Thêm `@Lazy` đôi khi tránh được việc **khởi tạo target đúng lúc đang mắc vòng**, nhưng không biến một thiết kế phụ thuộc vòng thành thiết kế tốt.

Thứ tự ưu tiên:

1. Tách bean executor ra khỏi business service và hạ tầng async config.
2. Đảm bảo executor **không phụ thuộc ngược** vào service sử dụng nó.
3. Dùng qualifier rõ ràng nếu có nhiều executor.
4. Chỉ khi thực sự cần trì hoãn reference, dùng `@Lazy` tại injection point hoặc `ObjectProvider`.
5. Tránh gọi service nghiệp vụ, truy cập DB, publish event hoặc start task từ constructor của `AsyncConfigurer`.
6. Nếu startup vẫn có vòng phụ thuộc, sửa dependency graph thay vì bật cơ chế cho phép circular references một cách mù quáng.

**Một hệ quả quan trọng:** nếu executor phục vụ cả request và background work, không nên bắt constructor executor đi lấy một service có `@Async` để thiết lập cấu hình. Executor là dependency của service, không nên ngược lại.

## 12. Các hiểu nhầm phổ biến về @Lazy

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| “Đánh `@Lazy` trên bean là chắc chắn nó chỉ tạo lúc request đầu tiên.” | Sai | Singleton eager khác có thể cần nó ngay lúc startup |
| “`@Lazy` tại injection point có thể tạo proxy trì hoãn lookup target.” | Đúng | Spring dùng lazy-resolution proxy cho dependency đó |
| “Nếu gọi method qua lazy proxy trong constructor thì vẫn lazy.” | Sai | Lần sử dụng thật có thể buộc resolve ngay |
| “ObjectProvider được inject nghĩa là target đã được tạo.” | Sai | Provider có thể được inject trước, target resolve lúc lookup |
| “Gọi `provider.getObject()` trong constructor vẫn bảo đảm không eager.” | Sai | Lúc gọi `getObject()` chính là lúc yêu cầu target |
| “AsyncConfigurer khởi tạo sớm nên mọi `@Async` sẽ chạy sai.” | Sai | Vấn đề phát sinh khi dependency/proxy/lifecycle xử lý không phù hợp |
| “`@Lazy` sửa được self-invocation `this.asyncMethod()`.” | Sai | Self-invocation bỏ qua proxy trong chế độ mặc định |
| “Bean executor tạo bằng `@Bean` có lifecycle quản lý bởi Spring.” | Thông thường đúng | Với một bean đầy đủ do context quản lý, Spring gọi lifecycle tương ứng |
| “Executor tự `new` bên trong hook thì đương nhiên được container đóng.” | Sai | Không phải Spring bean nếu chỉ trả object tự tạo không đăng ký |

Tài liệu `@Lazy` injection points và giới hạn eager dependency: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/annotation/Lazy.html

## 13. Cách chẩn đoán ứng dụng có nghi vấn khởi tạo sớm

Nếu sau khi thêm `AsyncConfigurer`, một service bỗng thiếu advice hoặc context không khởi động, hãy phân tích theo thứ tự:

**Bước 1 — Vẽ dependency graph thật ngắn.** Ghi các bean trực tiếp phụ thuộc vào `AsyncConfigurer`, executor, logger/metrics service, business service và các dependency ngược lại. Mục tiêu là tìm đường kéo một service lên trước khi post-processor sẵn sàng.

**Bước 2 — Xác nhận configurer là nguồn tạo sớm.** Tạm tách executor thành một `@Bean` độc lập và dùng `@Async("beanName")` cho đường gọi cần kiểm thử. Nếu lỗi biến mất, đây là bằng chứng hữu ích về dependency/lifecycle (nhưng vẫn cần hiểu nguyên nhân, không kết luận chỉ từ tương quan).

**Bước 3 — Xem cảnh báo BeanPostProcessor.** Nếu log có câu kiểu “not eligible for getting processed by all BeanPostProcessors”, kiểm tra bean nào bị tạo sớm và hạ tầng nào đang yêu cầu nó. Không mặc định mọi cảnh báo đều là lỗi AOP; chúng là tín hiệu cần kiểm chứng.

**Bước 4 — Xác minh proxy ở đường gọi.** Đảm bảo service đang được inject bởi Spring chứ không phải `new`; kiểm tra self-invocation và qualifier. Khi cần, dùng `AopUtils.isAopProxy(bean)` hoặc inspect proxy/advisor trong test, nhưng nhớ rằng **không phải mọi bean đều phải có AOP proxy**.

**Bước 5 — Kiểm tra behavior chứ không chỉ lớp bean.** Với `@Async("reportExecutor")`, có thể ghi thread name prefix từ method, cùng với callback Future/exception và test gọi qua bean khác. Với `@Transactional`, dùng test có transaction boundary rõ ràng và quan sát commit/rollback, không chỉ kiểm tra annotation tồn tại.

**Bước 6 — Phân biệt startup lỗi và runtime lỗi.** Lỗi thiếu bean/vòng dependency ngay lúc refresh context khác với việc worker chạy sai thread ở runtime. `@Lazy` có thể trì hoãn lỗi cấu hình tới lần gọi đầu, nên test integration cần exercise đường sử dụng.

**Bước 7 — Không để giải pháp làm mất lifecycle.** Khi tách hoặc thay executor, xác minh pool được khởi tạo, shutdown đúng, core/max/queue/rejection policy và exception handler vẫn đúng.

### Một checklist test tích hợp thực tế

Trong integration test Spring Boot có thể đặt:

- **Startup check:** `ApplicationContext` refresh thành công với `@EnableAsync`/bean executor.
- **Proxy check:** gọi `@Async` từ bean khác và xác nhận thread name prefix/tín hiệu Future hoàn tất theo kỳ vọng.
- **Advice check:** nếu service liên quan cần `@Transactional` hoặc cache/security advice, kiểm tra bằng hành vi thực tế của advice.
- **Lazy check:** một dependency chưa bị gọi từ constructor/configurer; instrument constructor hoặc log với test fixture để kiểm tra số lần/timing khởi tạo khi cần.
- **Failure check:** khi executor bị từ chối, exception tại submit phải được xử lý; khi worker ném lỗi, Future/handler phải báo đúng đường.
- **Shutdown check:** context đóng và bean executor giải phóng resource phù hợp.

Đừng viết test phụ thuộc vào thứ tự in log của nhiều worker. Dùng `CountDownLatch` hoặc `CompletableFuture` để đợi trạng thái xác định.

## 14. Những lỗi thường gặp

**Lỗi 1 — Inject một service AOP phức tạp thẳng vào constructor `AsyncConfigurer`.** Có thể khiến service tạo quá sớm. Ưu tiên executor bean riêng, lazy injection hoặc provider khi thật sự cần.

**Lỗi 2 — Chỉ đặt `@Lazy` lên class service rồi coi mọi eager resolution đã hết.** Nếu singleton eager cần target, container vẫn phải thỏa dependency; placement của `@Lazy` rất quan trọng.

**Lỗi 3 — Gọi `ObjectProvider.getObject()` ngay trong constructor configurer.** Provider không còn giúp dời thời điểm resolve.

**Lỗi 4 — Gọi method trên lazy proxy ở `@PostConstruct` lúc bootstrap.** Target vẫn có thể bị tạo sớm ngay tại lần dùng.

**Lỗi 5 — Dùng `@Async("executorName")` nhưng bean executor không có tên đúng.** Lỗi chọn executor khác với vấn đề early initialization.

**Lỗi 6 — Gọi `this.asyncMethod()` rồi cho rằng `AsyncConfigurer` hỏng.** Self-invocation bỏ qua advice khi `AdviceMode.PROXY`.

**Lỗi 7 — Định nghĩa executor tự `new` mà không initialize/shutdown.** Dễ thiếu lifecycle và rò rỉ thread khi context đóng.

**Lỗi 8 — Đặt business logic hoặc query DB bên trong `getAsyncExecutor()`.** Hook cấu hình infrastructure không phải nơi thực hiện side effect nghiệp vụ.

**Lỗi 9 — Cho executor phụ thuộc vào service đang dùng executor ấy.** Tạo vòng dependency hoặc startup behavior khó đoán.

**Lỗi 10 — Tin rằng có một `AsyncConfigurer` là mọi method chắc chắn dùng nó.** `@Async("qualifier")` có thể chọn executor riêng; cần kiểm tra routing.

**Lỗi 11 — Cho rằng `@Async void` sẽ ném exception về HTTP caller.** Với `void`, cần handler/log/metric; với Future, caller phải quan sát result/exception.

**Lỗi 12 — Sửa startup bằng cách bật circular references hoặc tắt advice.** Có thể che triệu chứng nhưng làm hệ thống khó bảo trì; nên sửa graph và kiểm chứng proxy.

**Lỗi 13 — Tạo nhiều AsyncConfigurer cạnh tranh trong một context.** Không nên dùng nhiều configurer cấp mặc định không có ý nghĩa phối hợp rõ ràng; nên hợp nhất cấu hình hoặc chọn executor qua qualifier.

**Lỗi 14 — Nhầm một cảnh báo BPP thành bằng chứng duy nhất.** Cần kết hợp stacktrace, thời điểm bean creation và test hành vi; không suy luận rằng mọi proxy đều đã hỏng.

## 15. Quyết định thiết kế theo nhu cầu

| Nhu cầu | Hướng thiết kế nên ưu tiên |
| --- | --- |
| Một method cần pool riêng | `@Bean("specificExecutor")` + `@Async("specificExecutor")` |
| Nhiều nhóm task cần isolation | Nhiều executor bean có qualifier cụ thể |
| Muốn chọn default executor cho `@Async` không qualifier | Bean theo quy tắc resolution hoặc `AsyncConfigurer` khi cần |
| Cần custom handler cho `@Async void` | `AsyncConfigurer#getAsyncUncaughtExceptionHandler()`, hạn chế dependency sớm |
| Configurer phải phụ thuộc bean phức tạp | Cân nhắc `@Lazy` tại injection point hoặc `ObjectProvider` và tránh dereference sớm |
| Cần dùng service có AOP proxy bên trong config | Tách logic nghiệp vụ ra khỏi infrastructure; chỉ truy cập khi context sẵn sàng |
| Task không chạy async khi tự gọi trong class | Sửa self-invocation/proxy boundary, không chỉ thêm `@Lazy` |
| Nghi ngờ BeanPostProcessor thiếu cơ hội xử lý | Kiểm tra early dependency resolution và proxy/advisor bằng integration test |
| Executor cần shutdown sạch | Đăng ký thành bean Spring quản lý; không chỉ trả object tự `new` không quản lý |

**Quy tắc thực dụng:** nếu không cần override executor mặc định hoặc exception handler toàn cục, **đừng triển khai `AsyncConfigurer` chỉ để chọn một thread pool cho một nhóm method**. Dùng named bean và qualifier, giúp loại bỏ phần lớn rủi ro cấu hình khởi tạo sớm.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao cấu hình class triển khai `AsyncConfigurer` có thể bị tạo trước các business singleton khác?

**Đáp án:** Spring cần đọc cấu hình async infrastructure trong quá trình bootstrap. Javadoc `@EnableAsync` cảnh báo configuration class `AsyncConfigurer` được khởi tạo sớm; các dependency bị yêu cầu eager ở giai đoạn này có thể chưa trải qua tất cả post-processor.

**Câu 2.** Cứ inject một service vào constructor `AsyncConfigurer` là chắc chắn `@Transactional` mất tác dụng?

**Đáp án:** Không. Đây là nguy cơ phụ thuộc thời điểm bootstrap, không phải quy tắc “100% mất proxy”. Cần xác minh dependency graph và behavior của bean trong context thực tế.

**Câu 3.** Sự khác nhau giữa `@Lazy` trên bean class và `@Lazy` tại constructor parameter?

**Đáp án:** `@Lazy` trên bean definition muốn trì hoãn bean tới lần đầu cần, nhưng singleton eager khác có thể buộc tạo nó lúc startup. `@Lazy` tại injection point có thể cung cấp lazy-resolution proxy, trì hoãn lấy target đến lần sử dụng.

**Câu 4.** Inject `ObjectProvider<Executor>` rồi gọi `getObject()` ngay trong constructor configurer có giải quyết vấn đề không?

**Đáp án:** Không. Bạn vẫn yêu cầu target được tạo tại thời điểm constructor. Lợi ích của provider chỉ tồn tại khi việc resolve thật sự được dời đến lúc thích hợp.

**Câu 5.** Một lời gọi `this.runAsync()` vẫn chạy trên caller thread dù executor đã cấu hình đúng. Có chứng minh AsyncConfigurer bị khởi tạo sớm dẫn đến lỗi không?

**Đáp án:** Không. Trong `AdviceMode.PROXY` mặc định, self-invocation bỏ qua proxy nên `@Async` interceptor không chạy. Đây là vấn đề đường gọi, không tự chỉ ra lỗi bootstrap.

**Câu 6.** Muốn method `generate` dùng pool `reportExecutor`, cách tối giản là gì?

**Đáp án:** Định nghĩa `@Bean("reportExecutor")` với `ThreadPoolTaskExecutor`, bật `@EnableAsync`, đánh dấu `@Async("reportExecutor")` và gọi method qua Spring proxy. Thường không cần `AsyncConfigurer`.

**Câu 7.** `getAsyncExecutor()` tạo `new ThreadPoolTaskExecutor()` và chỉ return thì pool đã là bean được Spring quản lý chưa?

**Đáp án:** Chưa chắc. Nếu object chỉ tự tạo trong hook, nó không mặc nhiên thành bean. Theo Javadoc, có thể thêm `@Bean` trên hook để quản lý lifecycle hoặc tốt hơn là tách một `@Bean` named executor rõ ràng.

**Câu 8.** Nếu lỗi startup biến mất sau khi thêm `@Lazy`, đã đủ để khẳng định ứng dụng an toàn chưa?

**Đáp án:** Chưa. Có thể lỗi chỉ bị trì hoãn đến lần đầu target được dùng. Cần integration test đường `@Async`, proxy/advice liên quan, handler, shutdown và behavior thực tế.

## Tóm tắt

- `AsyncConfigurer` tùy biến executor mặc định và exception handler cho `@Async void`.
- **Class triển khai `AsyncConfigurer` có thể được Spring khởi tạo rất sớm**, nên eager injection của bean phức tạp có thể gây vấn đề với lifecycle và hậu xử lý/proxy.
- **`@Lazy` tại injection point** hoặc **`ObjectProvider`** giúp trì hoãn việc resolve target, nhưng sẽ mất tác dụng nếu gọi target ngay trong constructor/pha khởi tạo.
- Đối với nhu cầu thông thường, **tách executor thành bean Spring quản lý và chọn bằng `@Async("beanName")`** là cách đơn giản, rõ ràng, ít phụ thuộc vào early configurer.
- Self-invocation, executor selection, AOP proxy creation và early initialization là **những vấn đề cần phân biệt**, không gộp vào một lỗi.
- Kiểm chứng bằng integration test **vòng đời + proxy + worker execution + exception + shutdown**, thay vì chỉ quan sát annotation hoặc tên thread.

## Tài liệu tham khảo

1. Spring Framework 6.2 Javadoc – `@EnableAsync`, cảnh báo khởi tạo sớm của `AsyncConfigurer` và `@Bean` trên `getAsyncExecutor()`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html
2. Spring Framework Javadoc – `AsyncConfigurer`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html
3. Spring Framework – Task Execution and Scheduling, `TaskExecutor` và `@Async`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
4. Spring Framework – Lazy-initialized Beans: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html
5. Spring Framework – `@Lazy` injection points: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/annotation/Lazy.html
6. Spring Framework – AOP proxying mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
