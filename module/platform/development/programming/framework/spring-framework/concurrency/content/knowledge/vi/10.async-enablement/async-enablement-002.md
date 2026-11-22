# Bean phải được container quản lý để annotation được xử lý

## 1. Ý chính trong một câu

Trong Spring Framework, ghi **`@Async` lên một phương thức Java không tự làm phương thức đó chạy trên thread khác**. Ở chế độ mặc định, Spring cần **quản lý bean**, bật xử lý bất đồng bộ bằng **`@EnableAsync`**, tạo hoặc gắn một **proxy** thích hợp và để **lời gọi đi qua proxy**. Nếu tự tạo đối tượng bằng `new` rồi gọi phương thức, annotation chỉ còn là metadata; Spring không tự chạy tới để chặn lời gọi.

~~~text
Đúng: caller ---> Spring-managed proxy ---> @Async interceptor
                                           |
                                           v
                                      TaskExecutor ---> worker thread
                                           |
                                           v
                                      target.method()

Sai kỳ vọng: caller ---> new Service().method()
                              |
                              v
                       lời gọi Java thường
                       (không qua proxy)
~~~

**Phân biệt hai điều kiện:**

1. **Bean phải thuộc Spring IoC container** để được các BeanPostProcessor của context phát hiện và xử lý annotation.
2. **Lời gọi phải đi qua cơ chế can thiệp thích hợp**. Trong chế độ `AdviceMode.PROXY` mặc định, gọi nội bộ `this.asyncMethod()` có thể bỏ qua proxy dù đối tượng đã là bean.

Bài này thuộc chủ đề **Bật @Async**. Trọng tâm là điều kiện container-managed bean, sự hình thành proxy, cách gọi đúng và các dấu hiệu để chẩn đoán khi `@Async` có vẻ không hoạt động. Thread pool, queue, transaction và propagation sẽ được nhắc trong chừng mực chúng giúp giải thích đúng ranh giới của annotation.

## 2. Vì sao Spring phải quản lý đối tượng?

### 2.1. Java annotation không tự thực thi logic

`@Async` là một annotation đánh dấu phương thức hoặc class có thể chạy bất đồng bộ. Nó không phải từ khóa Java bắt buộc JVM mở thread, cũng không đổi bytecode của một object do bạn `new` một cách tự động.

Trong cấu hình proxy mặc định, Spring dùng hạ tầng annotation-processing và AOP để áp dụng interceptor cho các **bean được đăng ký trong ApplicationContext**. Một caller nhận reference đến bean đã xử lý (thường là proxy). Khi caller gọi phương thức có `@Async` qua reference này, interceptor chọn executor và gửi công việc để chạy trên worker.

Ví dụ **sai kỳ vọng**:

~~~java
public class EmailService {
    @Async
    public void send(String address) {
        System.out.println(Thread.currentThread().getName());
    }
}

// Ở một lớp khác:
EmailService service = new EmailService();
service.send("user@example.test"); // gọi đồng bộ trên thread hiện tại
~~~

Đây là các **mảnh code minh họa**, không phải chương trình độc lập (cần import `@Async` và đặt lời gọi trong method). Đối tượng do `new EmailService()` tạo ra **không được Spring đăng ký/quản lý**, vì vậy không được hạ tầng `@Async` của context tự động tạo proxy.

Kết quả là `send()` chạy như Java thông thường. Nó có thể in tên main thread hoặc request thread; việc có annotation trong source code không thay đổi đường thực thi này.

### 2.2. Container quản lý bean khác gì so với chỉ có object trong JVM?

| Tình huống | Có phải bean Spring quản lý? | `@Async` có cơ hội được xử lý? |
| --- | --- | --- |
| Class được `@Component`/`@Service` và nằm trong vùng `@ComponentScan` đang hoạt động | Có | Có, khi bật `@EnableAsync` cùng context và lời gọi qua proxy |
| Object được phương thức `@Bean` trả về và đăng ký trong context | Có | Có, miễn các điều kiện proxy/lifecycle phù hợp |
| Object được đăng ký bằng cơ chế bean registration hợp lệ của Spring | Có | Có, nếu được đi qua các post-processor cần thiết |
| Object được tạo bằng `new MyService()` trong controller rồi gọi trực tiếp | **Không** | **Không** nhờ annotation `@Async` |
| Đối tượng được lưu trong static field nhưng chưa đăng ký thành Spring bean | Không | Không |
| Bean nằm trong một ApplicationContext khác, nơi chưa bật xử lý async | Có trong context đó | Chưa chắc; `@EnableAsync` có hiệu lực theo context |
| Bean có `@Async`, nhưng gọi bằng `this.method()` từ trong chính bean | Có | Lời gọi nội bộ thường **không được intercept** trong proxy mode |

Cụm "**do Spring quản lý**" không đồng nghĩa bắt buộc phải viết `@Service`. Spring có nhiều cách tạo và đăng ký bean. **Điều quyết định là instance dùng để gọi có đi qua cơ chế quản lý và AOP của context hay không.**

## 3. Đăng ký bean đúng cách để @Async được xử lý

### 3.1. @Service hoặc @Component và component scanning

Cách thường dùng trong ứng dụng Spring Boot:

~~~java
@Service
public class InvoiceService {
    @Async("invoiceExecutor")
    public CompletableFuture<String> generate(long invoiceId) {
        // Chạy trên executor được chỉ định khi được gọi qua proxy.
        return CompletableFuture.completedFuture("invoice-" + invoiceId);
    }
}
~~~

Đây là đoạn minh họa cần các import tương ứng, `@EnableAsync` và bean tên `invoiceExecutor`. Khi app có component scan bao phủ package chứa `InvoiceService`, bean sẽ được Spring đăng ký. Hãy **inject bean này** vào một bean khác, thay vì khởi tạo thủ công.

~~~java
@Service
public class BillingFacade {
    private final InvoiceService invoiceService;

    public BillingFacade(InvoiceService invoiceService) {
        this.invoiceService = invoiceService;
    }

    public CompletableFuture<String> startInvoice(long id) {
        return invoiceService.generate(id);
    }
}
~~~

Lời gọi từ `BillingFacade` tới `InvoiceService` đi qua reference Spring đã inject; trong cấu hình proxy phù hợp, `generate()` được dispatch tới executor. **Constructor injection** giúp rõ ràng dependency và giảm nguy cơ vô tình gọi object không do Spring quản lý.

Nhưng chỉ ghi `@Service` lên class **chưa đủ** nếu package không được scan, cấu hình scan sai, bean bị loại bằng profile/condition hoặc caller lại dùng `new InvoiceService()`. Khi chẩn đoán, cần kiểm tra **bean thực sự tồn tại trong ApplicationContext** và reference đang dùng có nguồn từ context.

### 3.2. @Bean có thể trả về object tạo bằng new — vẫn được quản lý

Một ngộ nhận là "hễ thấy từ khóa `new` thì `@Async` không hoạt động". Điều đúng là **nơi nào sở hữu object sau khi tạo**:

~~~java
@Configuration
@EnableAsync
public class WorkerConfig {
    @Bean
    public ExportWorker exportWorker() {
        return new ExportWorker(); // giá trị trả về được đăng ký làm Spring bean
    }
}
~~~

Đây là đoạn cấu hình minh họa, không độc lập. Object được tạo bằng `new` **bên trong phương thức `@Bean`** rồi được Spring tiếp nhận quản lý như bean. Nó khác với controller tự `new ExportWorker()` và giữ tham chiếu riêng ngoài context.

Không nên **gọi trực tiếp phương thức factory** `new WorkerConfig().exportWorker()` rồi kỳ vọng object trả về đã qua post-processing. Hãy inject bean hoặc lấy qua context đúng cách.

**Lưu ý khác:** dùng `@Async` trực tiếp trên **phương thức khai báo trong class `@Configuration`** không phải cách được Spring hỗ trợ để chạy logic nghiệp vụ bất đồng bộ. Đặt `@Async` trên method của **service bean**, còn `@Configuration` chịu trách nhiệm khai báo infrastructure và bean.

### 3.3. Context nào bật @EnableAsync?

Cấu hình tối thiểu:

~~~java
@Configuration
@EnableAsync
public class AsyncConfig {
    // Có thể khai báo một TaskExecutor tại đây.
}
~~~

Khi được Spring nạp vào ApplicationContext, `@EnableAsync` bật cơ chế annotation-driven asynchronous method execution cho context tương ứng. Trong Spring Boot, có thể đặt annotation này trên một `@Configuration` hoặc class khởi động phù hợp.

Nếu ứng dụng có **nhiều ApplicationContext** (ví dụ root context và context riêng của DispatcherServlet trong một số kiến trúc), `@EnableAsync` ở context này **không mặc nhiên áp dụng cho toàn bộ bean của các context khác**. Phải xác định chính xác service thuộc context nào và hạ tầng async đang hoạt động ở đâu.

## 4. Hai tầng cần đúng: đăng ký bean và lời gọi qua proxy

Tưởng tượng Spring chứa:

~~~text
ApplicationContext
    |
    +-- Async infrastructure: @EnableAsync
    |
    +-- Bean definition: invoiceService
            |
            +-- Tạo target InvoiceService
            +-- BeanPostProcessor kiểm tra @Async
            +-- Cung cấp reference proxy cho consumer
                    |
Caller ---------> proxy.generate(42)
                    |
                    +-- chọn TaskExecutor
                    +-- submit phần thực thi
                              |
                              v
                         worker thread
                              |
                              v
                         InvoiceService.generate(42)
~~~

Đây là **sơ đồ khái niệm**, không hứa Spring luôn dùng đúng một hình dạng proxy hoặc mọi phase diễn ra theo thứ tự giản lược trên. Spring AOP có thể dùng **JDK dynamic proxy** hoặc **class-based proxy** tùy interface, cấu hình và các proxy đã tồn tại.

**Điểm hay bị nhầm:**

- **Bean có annotation** không bảo đảm **mọi** lời gọi của nó đều chạy async.
- **Một method chạy trên thread khác** không nhất thiết là bằng chứng `@Async` đã chạy; caller cũng có thể tự dùng `ExecutorService`.
- **Tồn tại TaskExecutor** trong context không có nghĩa `@EnableAsync` đã bật hoặc `@Async` chắc chắn sử dụng đúng pool đó.
- **Gọi qua proxy** quyết định có interception ở chế độ mặc định hay không; scope singleton/prototype không tự sửa vấn đề interception.

Một ứng dụng có thể gặp cả hai lỗi cùng lúc: tự `new` service và quên bật `@EnableAsync`. Cách chẩn đoán phải kiểm tra từng điều kiện riêng.

## 5. Lỗi tự gọi phương thức (self-invocation)

Đây là lỗi phổ biến **ngay cả khi bean đã được Spring quản lý**:

~~~java
@Service
public class ImportService {
    public void startImport() {
        this.importAsync(); // gọi nội bộ, thường không qua proxy
    }

    @Async
    public void importAsync() {
        // Tác vụ dự kiến chạy nền, nhưng có thể chạy đồng bộ.
    }
}
~~~

Đoạn này là mã minh họa cần import và `@EnableAsync`. Khi `startImport()` đang chạy bên trong **target** của bean, `this.importAsync()` là lời gọi Java nội bộ. Nó không đi qua proxy Spring được caller nắm giữ, nên advice của `@Async` thường không được kích hoạt.

**Cách thiết kế khuyến nghị:** đưa nhiệm vụ bất đồng bộ vào bean riêng và inject qua constructor:

~~~java
@Service
public class ImportWorker {
    @Async("importExecutor")
    public CompletableFuture<Void> runAsync() {
        // Thực thi tác vụ.
        return CompletableFuture.completedFuture(null);
    }
}

@Service
public class ImportFacade {
    private final ImportWorker worker;

    public ImportFacade(ImportWorker worker) {
        this.worker = worker;
    }

    public CompletableFuture<Void> startImport() {
        return worker.runAsync(); // gọi qua proxy được inject
    }
}
~~~

Các class trên là **mã minh họa cần bổ sung import và cấu hình executor**, không trùng với demo độc lập ở mục 8. Phương án tách bean làm ranh giới bất đồng bộ hiển thị rõ, dễ kiểm thử và hạn chế dependency vòng.

Một số cách như tự inject chính bean của mình, lấy `AopContext.currentProxy()` hay bật circular references để gọi qua proxy **không phải lựa chọn mặc định nên dùng**. Chúng làm code phụ thuộc cơ chế AOP, khó bảo trì và có thể phát sinh vấn đề vòng đời.

Nếu chọn **`@EnableAsync(mode = AdviceMode.ASPECTJ)`** với spring-aspects và compile-time/load-time weaving được cấu hình đúng, Spring có thể can thiệp cả self-invocation; đây là **chế độ khác** với proxy mode mặc định, không phải giải pháp chỉ cần đổi một thuộc tính rồi hoạt động ngay.

## 6. Private, final, static, constructor và lifecycle callback

Proxy-based AOP có những ranh giới kỹ thuật. Khi thiết kế method `@Async`, cách đơn giản và dễ dự đoán là:

- Dùng **method public, không final** trên **bean do Spring quản lý**.
- Gọi method đó **từ bean khác qua reference đã được inject**.
- Đảm bảo class có thể được proxied nếu Spring cần class-based proxy.
- Tránh mong chờ advice cho **private method**, **static method**, **constructor**, hoặc code chạy **trước khi proxy sẵn sàng**.

Ví dụ sai:

~~~java
@Service
public class StartupService {
    @PostConstruct
    void init() {
        initializeAsync(); // thời điểm lifecycle, gọi nội bộ
    }

    @Async
    private void initializeAsync() {
        // Không nên kỳ vọng được Spring proxy intercept.
    }
}
~~~

Đây là mảnh minh họa (cần import `@PostConstruct` của Jakarta, `@Service`, `@Async`). Vừa là private method, vừa được gọi nội bộ trong lifecycle callback. `@Async` **không được dùng như cơ chế bất đồng bộ cho chính callback `@PostConstruct`**.

Nếu thực sự cần khởi động tác vụ nền sau khi app sẵn sàng, có thể sử dụng **ApplicationReadyEvent** trong Spring Boot hoặc một bean điều phối riêng để gọi method `@Async` trên bean khác, đồng thời quy định rõ khi nào hệ thống coi việc khởi tạo đã hoàn tất. Không khởi động tác vụ nền trước khi các dependency/context đã ở trạng thái phù hợp.

**Final và proxy:** class-based proxy không thể override final method; một class final cũng gây hạn chế với subclass proxy. JDK dynamic proxy chủ yếu expose các method qua interface tương ứng, nên việc inject theo class concrete có thể không phù hợp. Đừng coi `proxyTargetClass=true` là cách vượt qua final/private; nó chỉ thay đổi cơ chế proxy.

## 7. @EnableAsync, executor và kiểu trả về phải tương thích

Spring chọn executor theo qualifier trên `@Async("beanName")`, cấu hình async và quy tắc tìm kiếm executor của phiên bản/context. Với ứng dụng có nhiều pool, chọn rõ ràng:

~~~java
@Bean("reportExecutor")
public ThreadPoolTaskExecutor reportExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(20);
    executor.setThreadNamePrefix("report-");
    return executor;
}
~~~

Đây là đoạn cấu hình trong class `@Configuration` có import thích hợp. Bean `ThreadPoolTaskExecutor` do Spring quản lý được initialize theo lifecycle. Hãy tránh tự `new ThreadPoolTaskExecutor()` ngoài container rồi quên gọi initialize/shutdown.

Các kiểu trả về hợp lệ của một method `@Async` thường là **`void`**, **`Future<T>`** hoặc **`CompletableFuture<T>`**. Với method trả Future, caller nhận một Future do cơ chế async cung cấp. Phần thân method thường tạo một handle hoàn tất/giá trị tạm thích hợp để interceptor bao bọc kết quả.

~~~java
@Async("reportExecutor")
public CompletableFuture<String> createReport(long id) {
    // Method này chạy trên worker khi được gọi qua proxy đúng cách.
    return CompletableFuture.completedFuture("report-" + id);
}
~~~

Đây là method minh họa trong một bean khác, không phải code trong `@Configuration`. Lời gọi `createReport(...).get()` sẽ đợi kết quả và có thể chặn caller; muốn giữ tính bất đồng bộ cần thiết kế composition/continuation thay vì chờ ngay trong request nếu không cần.

Với `@Async void`, lỗi chạy trong worker không thể tự ném lại cho caller đã trả về; cần logger/`AsyncUncaughtExceptionHandler` hoặc một hợp đồng khác. Với Future, caller cần quan sát completion/exception và timeout. Executor có thể bị quá tải/từ chối task; `@Async` **không phải hàng đợi bền vững** và không hứa task luôn được thực hiện.

## 8. Ví dụ hoàn chỉnh: new, bean proxy, self-invocation, gọi qua bean khác

Demo **chạy được với Java 17+, Gradle và Spring Framework 6.1.14**, không cần Spring Boot hay máy chủ web. Ta cố ý cho cùng một class `ReportWorker` được sử dụng theo bốn đường:

1. `new ReportWorker()`: ngoài container, `@Async` bị bỏ qua.
2. `context.getBean(ReportWorker.class)`: trả về reference được Spring xử lý; gọi method `@Async` qua proxy.
3. Gọi `selfCall()` trên managed bean: method thường tự gọi `this.threadNameAsync()` bên trong target, không qua proxy.
4. Một bean khác inject `ReportWorker` và gọi qua reference đã inject: đúng ranh giới proxy.

### 8.1. Cấu trúc tệp

~~~text
async-bean-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AsyncBeanDemo.java
~~~

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'async-bean-demo'
~~~

Tệp **build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
}

application {
    mainClass = 'demo.AsyncBeanDemo'
}
~~~

Tệp **src/main/java/demo/AsyncBeanDemo.java**:

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class AsyncBeanDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            String callerThread = Thread.currentThread().getName();

            // Object Java thông thường: annotation không được xử lý.
            ReportWorker unmanaged = new ReportWorker();
            String unmanagedThread = unmanaged.threadNameAsync()
                    .get(5, TimeUnit.SECONDS);
            System.out.println("new runs on caller: " +
                    callerThread.equals(unmanagedThread));

            // Bean được xử lý và trả về từ Spring container.
            ReportWorker managed = context.getBean(ReportWorker.class);
            System.out.println("managed is proxy: " +
                    AopUtils.isAopProxy(managed));

            // Lời gọi bên ngoài qua proxy kích hoạt @Async.
            String managedThread = managed.threadNameAsync()
                    .get(5, TimeUnit.SECONDS);
            System.out.println("external call uses pool: " +
                    managedThread.startsWith("demo-worker-"));

            // Lời gọi this.threadNameAsync() bên trong cùng target.
            String selfThread = managed.selfCall()
                    .get(5, TimeUnit.SECONDS);
            System.out.println("self-call stays on caller: " +
                    callerThread.equals(selfThread));

            // Một bean khác nhận managed proxy bằng constructor injection.
            DelegatingCaller caller = context.getBean(DelegatingCaller.class);
            String delegatedThread = caller.call()
                    .get(5, TimeUnit.SECONDS);
            System.out.println("injected caller uses pool: " +
                    delegatedThread.startsWith("demo-worker-"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {

        @Bean("demoExecutor")
        public ThreadPoolTaskExecutor demoExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("demo-worker-");
            return executor;
        }

        // Có 'new' ở đây nhưng giá trị trả về là Spring-managed bean.
        @Bean
        public ReportWorker reportWorker() {
            return new ReportWorker();
        }

        @Bean
        public DelegatingCaller delegatingCaller(ReportWorker worker) {
            return new DelegatingCaller(worker);
        }
    }

    public static class ReportWorker {

        @Async("demoExecutor")
        public CompletableFuture<String> threadNameAsync() {
            String current = Thread.currentThread().getName();
            return CompletableFuture.completedFuture(current);
        }

        public CompletableFuture<String> selfCall() {
            return this.threadNameAsync(); // Bỏ qua proxy khi self-invoke.
        }
    }

    public static class DelegatingCaller {
        private final ReportWorker worker;

        public DelegatingCaller(ReportWorker worker) {
            this.worker = worker;
        }

        public CompletableFuture<String> call() {
            return worker.threadNameAsync();
        }
    }
}
~~~

### 8.2. Chạy và kết quả

Từ thư mục `async-bean-demo`, có JDK 17+ và Gradle được cài:

~~~bash
gradle run
~~~

Nếu có Gradle Wrapper, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows.

Với điều kiện executor hoạt động bình thường và task hoàn thành trước timeout năm giây, **năm dòng do chương trình tự in** là:

~~~text
new runs on caller: true
managed is proxy: true
external call uses pool: true
self-call stays on caller: true
injected caller uses pool: true
~~~

Gradle và các thư viện có thể in thêm thông báo build/log. Ví dụ dùng kiểm tra boolean thay vì in số thứ tự worker để kết quả không phụ thuộc việc pool tạo `demo-worker-1` hay `demo-worker-2`. Nếu task bị từ chối hoặc hệ thống quá tải, `get(timeout)` có thể ném ngoại lệ; demo giả định runtime chạy bình thường.

### 8.3. Điều cần quan sát

- `unmanaged` là object do code tạo trực tiếp; Spring không biết tới object này. Method vẫn trả `CompletableFuture`, nhưng được tạo **ngay trên caller thread**. Chỉ nhìn thấy kiểu Future không chứng minh method được gửi đến executor.
- `managed` lấy từ `ApplicationContext` là bean đã qua post-processing. Vì `ReportWorker` không khai báo interface, Spring dùng một dạng class-based proxy phù hợp trong demo; `AopUtils.isAopProxy(managed)` trả true.
- `managed.threadNameAsync()` là lời gọi từ bên ngoài qua proxy, nên nội dung method chạy trên thread có prefix `demo-worker-`.
- `managed.selfCall()` không có `@Async`; method chạy đồng bộ, và lời gọi `this.threadNameAsync()` bên trong target **không qua proxy**, vì vậy `threadNameAsync()` chạy trên caller.
- `DelegatingCaller` là bean khác; nó nhận `ReportWorker` do Spring inject và gọi method qua proxy, nên async hoạt động.
- `@Bean` tạo object bằng `new` **không làm object mất tính managed**: khác biệt là instance trả về được container đăng ký và post-process.
- `try-with-resources` đóng context sau khi Future đã hoàn tất, giúp Spring quản lý lifecycle của executor.

Code ở mục 8 là **chương trình hoàn chỉnh**; các đoạn ngắn ở các mục trước là **minh họa cần context/import bổ sung**, không nên copy riêng lẻ và kỳ vọng chúng tự chạy.

## 9. Gọi đúng bean trong ứng dụng web và ứng dụng có nhiều lớp

Trong một Spring MVC hoặc Spring Boot application, controller thường đã là bean do Spring quản lý. Nhưng nếu controller tự tạo service bằng `new`, service đó vẫn nằm ngoài cơ chế xử lý annotation:

~~~java
@RestController
public class ExportController {
    @GetMapping("/export")
    public String wrong() {
        ExportService service = new ExportService();
        service.exportAsync(); // @Async không được Spring intercept.
        return "submitted";
    }
}
~~~

Đây là ví dụ **sai có chủ đích**, chưa phải mã đầy đủ. Controller thuộc Spring không khiến mọi object do controller tạo ra **tự trở thành bean**.

Cách đúng là inject service:

~~~java
@RestController
public class ExportController {
    private final ExportService service;

    public ExportController(ExportService service) {
        this.service = service;
    }

    @PostMapping("/export")
    public ResponseEntity<Void> start() {
        service.exportAsync(); // reference tới Spring-managed proxy
        return ResponseEntity.accepted().build();
    }
}
~~~

Đoạn này cũng là minh họa, cần định nghĩa `ExportService`, `@EnableAsync` và các import. Một HTTP 202 chỉ nên hứa "**đã tiếp nhận yêu cầu**" nếu hệ thống có contract tương ứng. `@Async` với executor trong bộ nhớ **không** tự đảm bảo công việc được lưu bền vững qua restart, nên endpoint production cần xác định rõ ý nghĩa "accepted".

Nếu một method chạy chậm, không nên chỉ gắn `@Async` vào controller handler mà không xem xét hợp đồng MVC, kiểu trả về và cơ chế async request. Thường tốt hơn tách việc nền sang service bean có giao diện rõ ràng, rồi lựa chọn cách trả kết quả phù hợp.

## 10. Vì sao đã có bean mà @Async vẫn không hoạt động?

Có một số nguyên nhân độc lập cần kiểm tra:

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Method in tên request/main thread | `new` service ngoài context | Inject bean đã đăng ký |
| Có `@Service` nhưng startup không thấy bean | Package ngoài `@ComponentScan`, profile/condition không phù hợp | Kiểm tra scan và bean registration |
| Bean tồn tại nhưng method chạy đồng bộ | Thiếu `@EnableAsync` trong context chứa bean | Bật async đúng context |
| Method được gọi từ chính class bằng `this` | Self-invocation bỏ qua proxy mặc định | Tách worker thành bean khác và inject |
| Method private/final/static hoặc class không proxy được | Proxy không intercept được method | Dùng public non-final instance method và cấu trúc proxied phù hợp |
| `@Async` đặt trên method của `@Configuration` | Đây không phải nơi annotation được hỗ trợ như service method | Tách logic sang bean service |
| Gọi lúc `@PostConstruct` | Lifecycle/self-invocation trước ranh giới proxy thích hợp | Điều phối từ bean khác sau khi khởi tạo |
| Không thấy prefix executor mong đợi | Method chọn executor khác, qualifier sai hoặc chưa qua proxy | Chỉ định `@Async("executorName")`, kiểm tra bean và luồng |
| Inject class concrete gặp lỗi với JDK proxy | Proxy expose interface, không phải concrete type | Inject interface thích hợp hoặc cấu hình proxy dựa trên class khi tương thích |
| `@Async` có chạy nhưng request vẫn đợi lâu | Caller lập tức `get()`/`join()` hoặc logic khác chặn | Xem lại chiến lược trả kết quả và điểm chờ |
| Lỗi background không ném tới caller | Method `void` và exception xảy ra trên worker | Dùng Future và theo dõi lỗi, hoặc AsyncUncaughtExceptionHandler |

**Cách chẩn đoán từng bước:**

1. In tên thread tại **đầu method** (chỉ khi chẩn đoán; không dùng tên thread làm điều kiện nghiệp vụ).
2. Xác nhận `@EnableAsync` đã được xử lý trong context thật của bean.
3. Kiểm tra bean có xuất hiện trong context và được inject từ context, không phải object tự new.
4. Kiểm tra đường gọi: là **bean khác -> proxy.method()** hay **this.method()**?
5. Xác nhận method có thể được proxy intercept (public/non-final là lựa chọn an toàn phổ biến).
6. Kiểm tra executor được chọn và dấu hiệu task bị từ chối/quá tải.
7. Quan sát exception/completion của `Future` nếu có.
8. Đừng bỏ qua cấu hình tests: unit test tạo object bằng `new` không phản ánh hành vi AOP; muốn kiểm tra proxy hãy chạy test có ApplicationContext phù hợp.

Với `AopUtils.isAopProxy(obj)` trong ví dụ chạy Spring, kết quả true chứng minh reference là AOP proxy, nhưng **không đủ một mình** để chứng minh lời gọi cụ thể được `@Async` intercept. Một bean có thể được proxy vì các advice khác; cần kiểm tra cả `@EnableAsync`, method và đường gọi.

## 11. Những ranh giới liên quan: transaction, context và thread safety

Khi method `@Async` được dispatch thành công:

- Worker thường là **thread khác** caller. **ThreadLocal** như request attributes, MDC hay security context **không tự động được sao chép** nếu không có cơ chế propagation.
- **Transaction đang gắn với thread của caller** không mặc nhiên theo worker. Nếu method async cần transaction riêng, xác định cách mở transaction và xử lý exception/commit ở ranh giới worker phù hợp.
- **Bean singleton** được chia sẻ giữa các worker: `@Async` không khiến mutable fields trong bean an toàn luồng; ưu tiên stateless service, immutable data và đồng bộ khi cần.
- **Executor có capacity hữu hạn**. Nếu quá tải, task có thể bị từ chối; dùng queue bounded, rejection policy rõ ràng và theo dõi trạng thái công việc.
- **Context có vòng đời**. Async task phụ thuộc bean có thể chạy khi shutdown nếu không cấu hình/kiểm soát phù hợp; không coi annotation là cơ chế bảo đảm task hoàn thành sau khi process kết thúc.

Các vấn đề trên **không phủ định** điều kiện gốc của bài: muốn annotation hoạt động theo cơ chế proxy mặc định, instance phải nằm trong Spring container và lời gọi phải đi qua proxy. Nhưng sau khi đạt hai điều kiện ấy, thiết kế concurrency vẫn cần xem xét độc lập.

## 12. Checklist trước khi dùng @Async trong code review

- [ ] `@EnableAsync` được bật trong **đúng ApplicationContext**.
- [ ] Class service được đăng ký bằng `@Service`/`@Component`, `@Bean` hoặc cơ chế bean registration phù hợp.
- [ ] Caller **inject** service bean, không tự `new` một instance khác.
- [ ] Lời gọi async đi qua **proxy**; không gọi bằng `this.asyncMethod()`.
- [ ] Method được thiết kế dễ proxy: public, không final; không đặt `@Async` vào lifecycle callback hay method trong `@Configuration`.
- [ ] Executor được chọn đúng bằng qualifier hoặc cấu hình async; giới hạn queue/threads/rejection được xác định.
- [ ] Kiểu trả về `void`/`Future`/`CompletableFuture` và chiến lược xử lý lỗi được chọn có chủ đích.
- [ ] Không giả định transaction, ThreadLocal, request context hoặc security context tự đi theo worker.
- [ ] Không đặt request-specific mutable state lên field singleton dùng chung.
- [ ] Có test chạy **trong ApplicationContext** để xác minh proxy thực sự thực thi.

## 13. Câu hỏi tự kiểm tra

1. **Một class có `@Service` nhưng bị `new` thủ công thì annotation `@Async` có hiệu lực không?** Không nhờ Spring AOP trên object ấy. Muốn Spring xử lý, phải dùng instance đã được Spring quản lý.
2. **Vì sao `return new ReportWorker()` trong phương thức `@Bean` lại khác với `new ReportWorker()` trong controller?** Object được `@Bean` trả về đi qua đăng ký và bean post-processing của context; object tự new trong controller thì không.
3. **Bean đã được Spring quản lý, vậy `this.runAsync()` có async không?** Thường không trong `AdviceMode.PROXY` mặc định vì self-invocation bỏ qua proxy.
4. **Có cần `@EnableAsync` không?** Có để bật xử lý annotation-driven async ở cấu hình Spring tương ứng, trừ khi hạ tầng tương đương đã được cấu hình rõ bằng cách khác.
5. **`@Async` có tạo thread mới mỗi lần không?** Không nhất thiết. Nó gửi task đến executor; ThreadPoolTaskExecutor có thể tái sử dụng worker.
6. **`CompletableFuture` chứng minh method đã chạy async chưa?** Không. Một method Java thông thường cũng có thể trả về Future đã hoàn tất đồng bộ.
7. **Có nên đặt `@Async` vào private method trong cùng bean không?** Không nên kỳ vọng proxy mode intercept được; tách sang public method trên bean khác.
8. **Có thể dùng AspectJ mode để can thiệp self-invocation không?** Có khi weaving và các phụ thuộc cần thiết được cấu hình đúng; đây không phải hành vi mặc định.
9. **Tại sao unit test gọi `new SomeService()` không quan sát async?** Vì test chỉ gọi object Java, không có Spring proxy/interceptor.
10. **Gọi `@Async` đã thành công có bảo đảm transaction, dữ liệu request và hoàn tất nghiệp vụ không?** Không; từng hợp đồng phải được thiết kế và kiểm soát riêng.

**Kết luận:** Spring xử lý `@Async` như một khả năng của **bean được container quản lý**, không phải như lệnh Java có hiệu lực trên mọi object. Với chế độ proxy mặc định, hai thao tác dễ nhớ nhất là **đăng ký service thành bean** và **gọi service qua reference đã được Spring inject từ bean khác**. Đây là nền tảng trước khi tinh chỉnh executor hoặc tối ưu concurrency.

### Tài liệu chính thức

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — EnableAsync API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework — Async API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework — Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
