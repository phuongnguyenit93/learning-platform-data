# Không trông cậy @Async trên callback @PostConstruct của chính bean

## 1. Bài học cốt lõi

Trong Spring Framework, `@PostConstruct` là **callback vòng đời bean**: container gọi phương thức này trong quá trình khởi tạo bean. `@Async` là **cơ chế interceptor**: trong chế độ mặc định dựa trên proxy, một lời gọi từ bên ngoài phải đi qua Spring proxy thì nhiệm vụ mới được gửi đến executor.

Hai cơ chế xảy ra ở **những thời điểm khác nhau**. Vì vậy, **không đặt `@Async` trên chính phương thức `@PostConstruct` rồi mong nó tự chạy nền**. Cũng không mong việc gọi `this.loadData()` trong `@PostConstruct` sẽ kích hoạt `@Async` trên `loadData()` của cùng bean.

Spring Framework nêu rõ: `@Async` không được hỗ trợ kết hợp với lifecycle callback như `@PostConstruct`; để khởi tạo bất đồng bộ, hãy dùng một **bean khởi phát riêng** gọi phương thức `@Async` trên bean đích. Với tác vụ nặng, cách đơn giản và an toàn hơn trong Spring Boot là khởi phát sau khi context đã được khởi tạo, chẳng hạn qua `ApplicationRunner` hoặc sự kiện `ApplicationReadyEvent`, rồi gọi **bean worker khác**.

Ví dụ dễ gặp:

- Ứng dụng khởi động và cần tải dữ liệu tham chiếu từ API.
- Developer viết `@PostConstruct @Async public void warmUp()` và nghĩ startup sẽ trả về ngay.
- Thực tế callback có thể chạy trực tiếp trên thread khởi tạo bean, kéo dài startup; nếu callback ném lỗi, startup có thể thất bại.
- Developer chuyển logic sang `@Async public void warmUp()` nhưng lại gọi `this.warmUp()` ngay từ `@PostConstruct`. Lời gọi vẫn không đi qua proxy, nên vẫn chạy đồng bộ.
- Cách sửa là có **đường gọi qua proxy của bean khác**, từ một thời điểm khởi phát hợp lý, có executor, timeout, xử lý lỗi và chính sách readiness rõ ràng.

Phạm vi: Java 17, Spring Framework 6.x, Spring Boot 3.3.x với `@EnableAsync` mặc định `AdviceMode.PROXY`. Với AspectJ weaving hoặc lifecycle tùy biến, một số chi tiết interceptor khác, nhưng nguyên tắc **không dựa vào `@Async` trên callback khởi tạo** vẫn hữu ích.

## 2. Phân biệt ba đối tượng: target bean, proxy và callback

Spring thường xây dựng một bean theo chuỗi khái quát:

1. Tạo instance của class (constructor).
2. Inject dependencies và thiết lập properties.
3. Chạy các `BeanPostProcessor` trước khởi tạo, trong đó có xử lý `@PostConstruct` do `CommonAnnotationBeanPostProcessor` phụ trách.
4. Chạy callback khởi tạo như `InitializingBean.afterPropertiesSet()` hoặc init method khi được khai báo.
5. Các post-processor sau khởi tạo có thể tạo AOP proxy bao quanh bean.
6. Những bean khác được inject một reference phù hợp, có thể chính là proxy; gọi public method qua reference này mới có cơ hội được async advice chặn.

Đây là sơ đồ **khái niệm**, không phải cam kết mọi extension của mọi Spring version có cùng thứ tự chi tiết nội bộ:

~~~text
Spring container
   |
   +-- new TargetBean()
   +-- inject dependencies
   +-- @PostConstruct chạy trên bean trong pha init
   +-- hoàn tất initialization / tạo proxy khi áp dụng
   |
   +-- expose Spring proxy -----> caller ở bean khác
                                      |
                                      +-- proxy intercept @Async
                                      +-- executor.execute(task)
                                      +-- worker thread chạy target method

Trong TargetBean:
@PostConstruct init() -> this.asyncMethod()
                          |
                          +-- gọi trực tiếp target, KHÔNG đi qua proxy
~~~

**Không có chuyện tự động "nhảy sang thread mới" chỉ vì bytecode method mang `@Async`.** Interceptor cần nhận lời gọi qua đúng proxy. Đây cũng là lý do code tự tạo bằng `new MyService()` hoặc self-invocation `this.method()` thường bỏ qua `@Async`.

**Lưu ý chính xác về `@PostConstruct`:** nó chạy ở giai đoạn bean chưa hoàn tất khởi tạo. Spring có thể tạo proxy cho *bean được expose* sau đó, nhưng callback không phải lời gọi ứng dụng từ ngoài vào proxy đã được dùng ổn định. Không nên dùng callback như một điểm dispatch background work tùy ý, càng không nên cố workaround bằng cách inject chính mình để lấy proxy: self-reference/circular dependency làm startup phức tạp và dễ hỏng.

## 3. Hai anti-pattern thường gặp

### 3.1. Gắn đồng thời @PostConstruct và @Async lên một method

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class CacheBootstrap {
    @PostConstruct
    @Async("bootstrapExecutor") // Không làm callback này chạy async.
    public void preload() {
        fetchAllRemoteRecords(); // Có thể giữ thread khởi tạo rất lâu.
    }

    private void fetchAllRemoteRecords() {
        // Đại diện cho I/O chậm, không phải ví dụ chạy độc lập.
    }
}
~~~

Nếu `fetchAllRemoteRecords()` kéo dài 20 giây, thời gian khởi tạo bean có thể tăng tương ứng. `@Async` không biến callback thành một job chạy nền. Trong Spring Boot 3 dùng import `jakarta.annotation.PostConstruct`, **không** dùng `javax.annotation.PostConstruct` của các dự án Spring cũ nếu dependency không tương thích.

### 3.2. @PostConstruct gọi @Async trên cùng bean

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class InventoryBootstrap {
    @PostConstruct
    public void init() {
        this.refreshAsync(); // Bỏ qua proxy: gọi trực tiếp trên cùng object.
    }

    @Async("bootstrapExecutor")
    public void refreshAsync() {
        // Ở đây vẫn có thể chạy trên thread của callback init().
    }
}
~~~

Đây là trường hợp **self-invocation**. Kể cả khi bean đã được proxy và gọi từ một method khác của chính target sau khi startup, `this.refreshAsync()` cũng không được proxy mode intercept; ở `@PostConstruct` còn thêm vấn đề thời điểm lifecycle.

Hãy phân biệt với lời gọi hợp lệ:

~~~java
// Trích đoạn minh họa nằm trong bean KHÁC, đã inject Spring proxy:
private final InventoryWorker worker;

public StartupTrigger(InventoryWorker worker) {
    this.worker = worker;
}

public void trigger() {
    worker.refreshAsync(); // Lời gọi tới bean khác qua proxy.
}
~~~

Đoạn trên chưa phải class đầy đủ; class `InventoryWorker` phải là Spring-managed bean và method `refreshAsync()` đủ điều kiện async.

## 4. Ví dụ đầy đủ, chạy được trên Java 17 và Spring Boot 3.3

Ví dụ minh họa **cả lỗi lẫn cách đúng trong một lần chạy**. Nó không dựa vào `Thread.sleep` để chứng minh việc chuyển thread. Executor riêng dùng prefix `init-worker-`; code ghi lại tên thread **ngay trong method thật**, rồi in kết quả boolean xác định.

### 4.1. Cấu trúc dự án

~~~text
lifecycle-async-demo/
├── pom.xml
└── src/main/java/com/example/lifecycle/
    ├── LifecycleAsyncApplication.java
    ├── WrongLifecycleBean.java
    └── WarmupWorker.java
~~~

### 4.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>lifecycle-async-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
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
~~~

`spring-boot-starter` cung cấp Boot và các dependency nền; `spring-boot-starter-aop` cho hạ tầng proxy AOP rõ ràng. `jakarta.annotation.PostConstruct` được dùng theo Spring Boot 3. Không cần web server hay database để chạy demo.

### 4.3. LifecycleAsyncApplication.java

~~~java
package com.example.lifecycle;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class LifecycleAsyncApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(
                             LifecycleAsyncApplication.class, args)) {
            // Đóng context sau khi ApplicationRunner hoàn tất.
        }
    }

    @Bean("initExecutor")
    ThreadPoolTaskExecutor initExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("init-worker-");
        pool.setWaitForTasksToCompleteOnShutdown(true);
        return pool;
    }

    @Bean
    ApplicationRunner afterStartup(WarmupWorker worker) {
        return args -> {
            System.out.println("RUNNER_ON_POOL="
                    + isWorkerThread());

            // Đây là lời gọi TỪ bean/runner khác vào Spring proxy.
            CompletableFuture<String> result = worker.prepare();

            // Runner cố ý chờ để demo có kết quả xác định.
            String actualThread = result.get(5, TimeUnit.SECONDS);
            System.out.println("SEPARATE_BEAN_ON_POOL="
                    + actualThread.startsWith("init-worker-"));
        };
    }

    private static boolean isWorkerThread() {
        return Thread.currentThread().getName().startsWith("init-worker-");
    }
}
~~~

Điểm quan trọng: `afterStartup` là một `ApplicationRunner`. Spring Boot gọi runner **sau khi ApplicationContext đã refresh** và các singleton cần thiết đã được tạo. `worker.prepare()` là lời gọi vào một **Spring-managed worker khác**, qua proxy của `@Async("initExecutor")`.

Runner cố ý dùng `get(5, TimeUnit.SECONDS)` chỉ để đảm bảo stdout demo có thứ tự, có hạn chờ và cho phép chương trình đóng context sạch. Nếu yêu cầu thực sự là “khởi động job nền rồi cho web server nhận request ngay”, **không nên chờ Future ngay trên startup thread**; phải có trạng thái job/readiness và cơ chế theo dõi riêng.

### 4.4. WrongLifecycleBean.java

~~~java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class WrongLifecycleBean {
    @PostConstruct
    @Async("initExecutor")
    public void initialize() {
        System.out.println("POST_CONSTRUCT_ON_POOL="
                + isWorkerThread());

        // Cùng bean, gọi this; @Async của method bên dưới bị bỏ qua.
        this.selfInvokedAsync();
    }

    @Async("initExecutor")
    public void selfInvokedAsync() {
        System.out.println("SELF_CALL_ON_POOL="
                + isWorkerThread());
    }

    private boolean isWorkerThread() {
        return Thread.currentThread().getName().startsWith("init-worker-");
    }
}
~~~

Hai giá trị được in tại chính callback và method gọi nội bộ, không phải kiểm tra một biến giả lập. Spring tạo `WrongLifecycleBean` trong lúc khởi tạo context, vì vậy hai dòng này xuất hiện trước các dòng từ `ApplicationRunner`.

Dù `initialize()` được đánh dấu cả `@PostConstruct` và `@Async`, callback vẫn không chạy qua async advice. Tương tự, `selfInvokedAsync()` không được gửi tới executor vì lời gọi là `this.selfInvokedAsync()`.

### 4.5. WarmupWorker.java

~~~java
package com.example.lifecycle;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class WarmupWorker {
    @Async("initExecutor")
    public CompletableFuture<String> prepare() {
        // Đọc thread name NGAY trong code thực tế của worker.
        String name = Thread.currentThread().getName();
        return CompletableFuture.completedFuture(name);
    }
}
~~~

Chữ ký trả `CompletableFuture<String>` phù hợp với `@Async`. Method implementation trả một completed future để Spring async proxy có thể lấy kết quả của task đã được executor chạy; caller nhận một Future đại diện cho công việc được gửi. Điều đó **không** có nghĩa implementation chạy trên caller: tên thread được lấy bên trong method và kết quả sẽ có prefix `init-worker-`.

### 4.6. Chạy và kết quả mong đợi

Yêu cầu JDK 17+ và Maven. Tại thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Bỏ qua log của Spring và Maven, **bốn dòng do chương trình in** theo thứ tự:

~~~text
POST_CONSTRUCT_ON_POOL=false
SELF_CALL_ON_POOL=false
RUNNER_ON_POOL=false
SEPARATE_BEAN_ON_POOL=true
~~~

Vì sao kết quả đáng tin?

1. `WrongLifecycleBean.initialize()` được container gọi trong lúc khởi tạo bean, trên luồng startup chứ không phải luồng của `initExecutor`. Do đó dòng đầu là `false`.
2. `this.selfInvokedAsync()` là lời gọi trực tiếp, không qua proxy, nên dòng thứ hai cũng là `false`.
3. `ApplicationRunner` chạy trên luồng ứng dụng khởi động bình thường, nên dòng thứ ba là `false`.
4. `WarmupWorker.prepare()` được gọi trên proxy của một bean khác sau startup và dùng đúng `initExecutor`; method thật chạy trên luồng có prefix `init-worker-`, cho dòng thứ tư là `true`.

Demo không đòi hỏi đồng thời nhiều worker để chứng minh đường đi proxy. Với `ThreadPoolTaskExecutor`, `corePoolSize=1`, `queueCapacity=8` chỉ mô tả cấu hình của **demo**, không phải mặc định của Spring. Ngoài ba file và `pom.xml` đã liệt kê, không cần các file code bí mật khác. Đây là ví dụ để **hiểu cơ chế**, không phải thiết kế thực hiện batch nặng thực tế.

## 5. Cách sửa ở môi trường thật

### 5.1. Ưu tiên khởi phát bằng ApplicationRunner

Spring Boot có `ApplicationRunner` và `CommandLineRunner` để thực thi code khi context đã được chuẩn bị và khởi động. Tách làm hai bean:

~~~java
// Trích đoạn trong bean khởi phát, không phải chương trình độc lập.
@Component
public class WarmupTrigger implements ApplicationRunner {
    private final CatalogWorker worker;

    public WarmupTrigger(CatalogWorker worker) {
        this.worker = worker;
    }

    @Override
    public void run(ApplicationArguments args) {
        worker.refreshCatalog(); // Caller đi qua proxy của bean KHÁC.
    }
}
~~~

Cần import `org.springframework.stereotype.Component`, `org.springframework.boot.ApplicationRunner` và `org.springframework.boot.ApplicationArguments`. `CatalogWorker` là bean service tách riêng, có public method `@Async("catalogExecutor")`. Đoạn trên không chờ kết quả; để xử lý production cần kiểm soát lỗi, retry/timeout và trạng thái hoàn tất.

Khi cần nhiều runner, dùng `@Order` hoặc `Ordered` để điều khiển thứ tự trong phạm vi runners, nhưng **không** biến mọi task async thành đã hoàn tất theo thứ tự ấy. Nếu runner A gửi job rồi trả về ngay, runner B có thể chạy khi job A vẫn đang xử lý.

### 5.2. Dùng @EventListener(ApplicationReadyEvent.class) khi cần bắt đầu sau runners

Trong Spring Boot, `ApplicationReadyEvent` được phát **sau khi các ApplicationRunner/CommandLineRunner đã được gọi**. Một listener có thể gọi worker khác:

~~~java
// Trích đoạn minh họa trong Spring-managed bean riêng.
@Component
public class ReadyTrigger {
    private final CatalogWorker worker;

    public ReadyTrigger(CatalogWorker worker) {
        this.worker = worker;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        worker.refreshCatalog();
    }
}
~~~

Cần import `org.springframework.context.event.EventListener`, `org.springframework.boot.context.event.ApplicationReadyEvent` và `org.springframework.stereotype.Component`. Với event listener thông thường, handler ban đầu chạy trong luồng publish event; trong đoạn trên **chính lời gọi `worker.refreshCatalog()` qua proxy** mới đưa phần nặng sang executor.

**Không nhầm “event ready đã phát” với “dữ liệu warm-up đã sẵn sàng”.** Nếu listener chỉ gửi một việc nền rồi trả ngay, Spring Boot vẫn có thể chuyển readiness sang nhận traffic trước khi công việc xong. Nếu API chỉ hoạt động đúng sau khi warm-up hoàn tất, phải có readiness gate, kiểm soát trạng thái khởi tạo hoặc startup đồng bộ có hạn định. Không dùng một cờ boolean không đồng bộ mà quên memory visibility.

Nếu context refresh lại hoặc ứng dụng có hierarchy nhiều context, phải chú ý sự kiện trùng lặp và idempotency của công việc khởi tạo. Với nhiều pod, mỗi pod có thể nhận sự kiện, nên job dùng chung toàn cụm cần cơ chế coordination.

### 5.3. Dùng bean khởi phát riêng với @PostConstruct — có điều kiện

Tài liệu Spring cũng mô tả mô hình một bean khởi tạo độc lập inject bean đích và gọi method async trong `@PostConstruct`:

~~~java
// Mô hình tối giản theo tài liệu; không phải chương trình Java độc lập.
@Component
public class CatalogInitializer {
    private final CatalogWorker worker;

    public CatalogInitializer(CatalogWorker worker) {
        this.worker = worker;
    }

    @PostConstruct
    public void initialize() {
        worker.refreshCatalog(); // Khác bean, reference có thể là proxy.
    }
}
~~~

So với `this.refreshCatalog()` trên cùng bean, lời gọi trên **có khả năng đi qua proxy của CatalogWorker** nếu bean đích đã được xây dựng và inject đúng. Tuy nhiên, `@PostConstruct` của bean khởi phát vẫn diễn ra trong pha tạo singleton. Nó không bảo đảm mọi dependency trong context đều đã sẵn sàng, có thể tạo vòng phụ thuộc, deadlock hoặc race nếu worker lập tức truy cập các bean/tài nguyên còn đang khởi tạo. Với tác vụ nặng, đa dependency hoặc yêu cầu startup rõ ràng, thường nên chọn runner/sự kiện sau refresh thay vì cố gắng dispatch trong lifecycle callback.

Nếu thật sự dùng biến thể này, hãy giữ initializer **chỉ làm nhiệm vụ dispatch**, tránh chờ `future.get()` bên trong `@PostConstruct` và kiểm thử startup có timeout/circular dependency.

### 5.4. Còn SmartInitializingSingleton hay ContextRefreshedEvent?

`SmartInitializingSingleton.afterSingletonsInstantiated()` chạy sau giai đoạn tạo các singleton không-lazy thông thường, do đó hữu ích nếu công việc cần các singleton sẵn sàng nhưng không cần đợi đến `ApplicationReadyEvent`. `ContextRefreshedEvent` diễn ra sau khi refresh context; listener có thể dispatch tới bean khác.

Hai hook này không thay thế mọi semantics startup: còn lazy beans, nhiều context, cơ chế refresh, trạng thái server/readiness và các task dispatch bất đồng bộ. Chọn hook theo **điều kiện phải hoàn thành trước khi chạy** và mức chấp nhận job nền, không dựa đơn thuần vào tên “after”.

## 6. Nếu công việc là bắt buộc trước khi ứng dụng sẵn sàng

Có hai thiết kế cần tách bạch:

| Mục tiêu | Điểm khởi phát | Điều kiện readiness | Cách xử lý lỗi |
| --- | --- | --- | --- |
| Khởi tạo nhẹ, bắt buộc, nhanh | `@PostConstruct` hoặc init method | Khởi tạo bean chỉ kết thúc sau công việc | Fail startup rõ ràng nếu không hợp lệ |
| Nạp dữ liệu bắt buộc trước khi phục vụ | `ApplicationRunner`, gọi nghiệp vụ (đồng bộ hoặc chờ Future **có timeout**) | Runner chỉ thành công khi việc bắt buộc thành công | Fail startup hoặc readiness REFUSING_TRAFFIC |
| Warm-up tùy chọn, có thể làm sau | `ApplicationReadyEvent` / runner dispatch async | Cho phép ứng dụng phục vụ trong trạng thái có fallback | Log, metric, retry/backoff, health status phù hợp |
| Batch chỉ cần chạy một lần trên toàn cluster | Job scheduler/queue/leader election, DB lease | Tùy contract chung | Idempotency, khóa/claim và trạng thái bền vững |

**Không nên lấy một @Async method làm bằng chứng tính sẵn sàng.** Một Future được tạo chứng minh có yêu cầu gửi task (và còn phải xử lý từ chối); nó không nói task đã hoàn thành.

Nếu runner chờ Future để chặn startup, phải có deadline:

~~~java
// Trích đoạn minh họa trong ApplicationRunner, không độc lập.
CompletableFuture<Void> job = worker.initializeRequiredData();

try {
    job.get(20, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    job.cancel(true); // Chỉ là yêu cầu hủy, không bảo đảm worker đã dừng.
    throw new IllegalStateException("Bắt buộc khởi tạo dữ liệu nhưng quá hạn", ex);
}
~~~

Cần import các kiểu từ `java.util.concurrent`; `initializeRequiredData()` ở đây là method do ứng dụng định nghĩa. Còn phải cân nhắc `ExecutionException` và `InterruptedException`: ghi nhận nguyên nhân lỗi, khôi phục interrupt flag khi bắt interrupted, rồi quyết định fail startup hay degraded readiness. `cancel(true)` không tự rollback giao dịch DB và không dừng tác vụ phớt lờ interrupt.

Spring Boot phát `ApplicationReadyEvent` sau runners, rồi có trạng thái readiness chấp nhận traffic nếu không có logic tùy chỉnh. Nếu runner chờ xong mới trả, bạn có thể bảo đảm startup không tuyên bố ready quá sớm, nhưng việc chờ cũng tăng thời gian deployment và có thể làm probe timeout. Chọn giới hạn phù hợp với nền tảng vận hành.

## 7. Phân biệt lỗi khởi tạo và lỗi trong tác vụ async

### 7.1. @PostConstruct ném lỗi có thể làm bean creation thất bại

~~~java
// Đoạn minh họa bên trong @Component.
@PostConstruct
public void checkConfiguration() {
    if (requiredEndpoint == null) {
        throw new IllegalStateException("Missing endpoint");
    }
}
~~~

Không cần `@Async` để kiểm tra một điều kiện đơn giản như trên. Nếu lỗi phát sinh trong callback, Spring có thể dừng tạo bean và từ đó khởi động context thất bại. Điều này hợp lý cho **điều kiện cấu hình bắt buộc** và là lý do nên giữ `@PostConstruct` ngắn, rõ và ổn định.

### 7.2. @Async void ném lỗi không quay về caller theo Future

~~~java
// Đoạn minh họa bên trong bean worker.
@Async("initExecutor")
public void refreshCatalog() {
    throw new IllegalStateException("remote service unavailable");
}
~~~

Nếu được gọi qua proxy và thực thi bằng executor bất đồng bộ, exception phát sinh trong worker. Với return type `void`, caller không có Future để nhận lỗi; Spring dùng `AsyncUncaughtExceptionHandler` (mặc định chủ yếu log lỗi). Với `CompletableFuture<T>`/`Future<T>`, caller có thể quan sát lỗi qua `get()/join()` hoặc completion callback.

Vì vậy, nếu warm-up quan trọng, **trả Future để giám sát trạng thái** thay vì fire-and-forget không ghi nhận. Trường hợp executor bão hòa và từ chối ngay tại submission còn có thể tạo `TaskRejectedException` tại caller. Đừng dùng silently-discard rejection policy cho tác vụ mà readiness hoặc Future phụ thuộc kết quả, vì job có thể mất mà Future không hoàn tất.

### 7.3. Không che giấu lỗi bằng callback khởi động

Nếu chọn dispatch từ `ApplicationReadyEvent` và sau đó không đợi, startup vẫn có thể báo ready dù warm-up lỗi. Với job tùy chọn, phải ghi log kèm job ID và đo metrics; với job bắt buộc, dùng readiness gate và fallback đúng yêu cầu nghiệp vụ. Một startup hook được gọi thành công không chứng minh remote data, cache hay DB snapshot đã sẵn sàng.

## 8. ThreadLocal, transaction, proxy và async thật sự

Sau khi sửa để lời gọi đi qua proxy, có thể xuất hiện những thay đổi mà test trước đây không phát hiện do callback chạy đồng bộ:

- **Transaction:** transaction association thuộc về thread; `@Transactional` của callback/caller không tự chuyển sang worker. Worker cần boundary transaction riêng, thường thông qua một service bean được Spring proxy quản lý. Không tự giữ JDBC connection/EntityManager qua threads.
- **MDC/trace/security:** `ThreadLocal` thường không tự truyền sang worker; capture các ID cần thiết rồi truyền qua tham số, hoặc cấu hình context propagation như `TaskDecorator`. Worker phải dọn context khi pool tái sử dụng thread.
- **Request scope:** lúc khởi động ứng dụng thường không có HTTP request. Đừng inject/use request-scoped bean trong callback startup như thể request context tồn tại.
- **Mutable object:** việc gửi task sang thread khác có thể tạo race nếu callback tiếp tục sửa object mà worker đang đọc. Dùng immutable snapshot hoặc đồng bộ hóa đúng.
- **Bean dependencies:** worker được inject là bean Spring quản lý nhưng có thể gọi đến service khác còn lazy hoặc có external resource chưa sẵn sàng; kiểm soát điều kiện và retry.
- **ThreadPoolTaskExecutor:** cấu hình core/max/queue, rejection, thread naming và graceful shutdown phù hợp; mặc định Framework hay Boot không bảo đảm một số luồng cố định trong mọi môi trường.

Tương tự, `@Async` trên method `private`/`final` hoặc trên class `final` có giới hạn proxy trong các phương thức proxy thông dụng; dùng **public, non-final** method trên Spring bean, được bean khác gọi. Việc bật `@EnableAsync` đúng `ApplicationContext` và gọi qua proxy là điều kiện quan trọng. Nếu dùng `SyncTaskExecutor`, lời gọi qua proxy có thể đã được intercept nhưng vẫn chạy trên **caller thread**, vì bản thân executor là synchronous. Do đó, khi chẩn đoán, phải xác minh cả **proxy path** và **executor implementation**, không chỉ nhìn thread name.

## 9. Chẩn đoán: @Async không chạy sau @PostConstruct

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra / sửa |
| --- | --- | --- |
| `@PostConstruct @Async` vẫn chạy trên main thread | Callback được gọi trong giai đoạn bean initialization, không qua async proxy | Bỏ `@Async` khỏi callback; dispatch từ runner/sự kiện sang bean worker khác |
| `this.asyncWork()` vẫn đồng bộ | Self-invocation bỏ qua proxy | Tách worker sang bean khác, inject proxy |
| Việc nền làm chậm khởi động | Callback làm I/O nặng trước khi init bean hoàn tất | Đưa sang post-refresh hook, timeout rõ |
| `@Async` có nhưng không thấy worker thread | Thiếu `@EnableAsync`, self-call, gọi object tự `new` hoặc dùng `SyncTaskExecutor` | Kiểm tra bean, interceptor, executor và thread prefix |
| Startup hiển thị ready nhưng dữ liệu chưa nạp | Async task chạy sau khi runner/listener trả về | Chọn readiness gate hoặc chờ Future có hạn định |
| Exception warm-up không làm startup fail | `void @Async` chạy tách biệt, lỗi vào uncaught handler | Trả CompletableFuture, xử lý failure và đánh giá readiness |
| Thỉnh thoảng deadlock khi startup | Chờ/khởi phát cross-bean từ `@PostConstruct` dưới singleton creation lock | Chuyển sang runner sau refresh, giảm circular dependency |
| Đã sửa sang worker bean nhưng @Transactional không đúng | Transaction context caller không đi theo worker | Định nghĩa transaction trên đường gọi trong worker |
| Test sync pass, production race | Worker thật chạy song song, mutable state chia sẻ | Dùng latch, immutable data, lock/transaction phù hợp |
| Có nhiều pod cùng warm-up | Startup hook chạy ở mỗi instance | Dùng idempotency hoặc coordination nếu cần chỉ một lần toàn cụm |

### Checklist trước khi merge

1. `@PostConstruct` chỉ validate config/khởi tạo trạng thái nhẹ, không làm I/O nặng và không dựa vào `@Async`.
2. Phương thức cần chạy nền nằm ở **Spring-managed bean khác**, được gọi từ một trigger thích hợp sau khi proxy sẵn sàng.
3. `@EnableAsync` được bật đúng context, và code không đi qua `this.method()` hoặc object tạo bằng `new`.
4. Executor được chỉ rõ (tên/qualifier) và có thread prefix để quan sát; queue/rejection/shutdown được xem xét.
5. Phương thức async có return type hợp lệ: `void`, `Future<T>` hoặc `CompletableFuture<T>`. Nếu startup phụ thuộc kết quả, không dùng `void` không có đường báo lỗi.
6. Có timeout, error handler, logging và trạng thái thất bại cho warm-up. Không giả định `Future.get(timeout)` tự cancel task.
7. Chính sách readiness tường minh: công việc có bắt buộc xong trước traffic không? Event/runner có trả trước khi công việc xong không?
8. Context/security/transaction và mutable state được thiết kế lại khi chuyển sang worker; không giả định giữ nguyên những gì có ở callback.
9. Test có xác minh **callback inline**, **self-call inline** và **cross-bean async thực sự**; test thêm overload và shutdown nếu job quan trọng.
10. Với multi-instance, job có thể được khởi phát nhiều lần; dùng idempotency, job ledger hoặc cluster coordination khi cần.

## 10. Bài tập tư duy

1. Vì sao `@PostConstruct @Async public void init()` không bảo đảm chạy nền dù bean có `@EnableAsync`?
2. Một method `load()` được đánh dấu `@Async`, nhưng `@PostConstruct` trong cùng bean gọi `this.load()`. Cần thay cấu trúc bean như thế nào để interceptor được áp dụng?
3. Lời gọi từ `ApplicationRunner` sang bean khác có gì khác với self-invocation? Khi nào runner nên đợi kết quả, khi nào nên trả ngay?
4. `ApplicationReadyEvent` được phát sau runners. Nếu listener gửi job rồi trả ngay, job đã hoàn tất khi readiness chấp nhận traffic chưa?
5. Tại sao `@Async void` có thể log lỗi mà không khiến startup thất bại? Nếu warm-up là bắt buộc, nên chọn kiểu return gì?
6. Một test chạy với `SyncTaskExecutor` thấy callback và worker cùng thread. Làm sao phân biệt proxy không kích hoạt với proxy đã kích hoạt nhưng executor đồng bộ?
7. Nếu một job warm-up tốn 30 giây và gọi DB chậm, nên cân nhắc timeout, retry, transaction và readiness ra sao?
8. Nếu ứng dụng có ba pod, việc chuyển từ `@PostConstruct` sang `ApplicationRunner` có tự ngăn ba pod cùng xử lý một job global không?

**Kết luận:** `@PostConstruct` là **callback của container trong pha tạo bean**, không phải điểm gọi ứng dụng qua Spring proxy. `@Async` trong proxy mode chỉ có ý nghĩa khi lời gọi đi qua proxy và executor phù hợp. Đừng đặt `@Async` trên chính lifecycle callback hoặc dựa vào `this.asyncMethod()`. Hãy dùng một trigger tách biệt sau khi bean sẵn sàng để gọi worker bean khác, đồng thời làm rõ quy tắc timeout, lỗi và readiness.

## Tài liệu tham khảo chính thức

- [Spring Framework — Task Execution and Scheduling, @Async](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — @PostConstruct / @PreDestroy](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html)
- [Spring Framework — Bean lifecycle and initialization](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Boot 3.3 — SpringApplication and Application Events](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Framework — @EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
