# Phân biệt đối tượng tự tạo bằng new với bean được tiêm

## 1. Mục tiêu: theo đúng đối tượng mà lời gọi thực sự đi qua

Trong Spring Framework, hai biến có thể cùng kiểu `ReportService` nhưng hành vi **khác hẳn nhau**:

- `new ReportService()` là đối tượng Java do code gọi constructor trực tiếp; không tự được Spring container quản lý.
- `ReportService` nhận qua constructor injection, `@Autowired`, hoặc `ApplicationContext.getBean(...)` là **bean reference** do container cung cấp. Tùy cấu hình, reference này có thể là **proxy**, thay vì đối tượng target thuần.

Sự phân biệt đặc biệt quan trọng trong chủ đề **Spring Framework - concurrency**, vì `@Async` ở chế độ mặc định dùng **Spring AOP proxy** để intercept lời gọi và submit task cho executor. Method có `@Async` trên một instance tự `new` thường chạy đồng bộ như method Java bình thường.

**Mục tiêu sau bài học:**

1. Giải thích khác nhau giữa đối tượng tự tạo, bean được đăng ký, và proxy được inject.
2. Nhận biết khi nào `@Async` thực sự chuyển execution sang executor, và khi nào annotation không được intercept.
3. Phân biệt `new` **bên ngoài container** với `new` **nằm trong method `@Bean`**: cả hai đều gọi constructor Java, nhưng chỉ trường hợp thứ hai được đăng ký làm Spring bean.
4. Viết constructor injection đúng cách, tránh tự `new` service có dependency và interceptor.
5. Hiểu self-invocation, proxy type, method visibility, scope và lifecycle.
6. Kiểm chứng thực tế bằng chương trình Java 17+ chạy với Spring Framework, thread name, proxy detection và test có điều phối.
7. Chọn được thiết kế không chia sẻ mutable state thiếu an toàn khi Spring singleton được gọi đồng thời.

**Phạm vi:** bean management, đường đi lời gọi và ảnh hưởng đến `@Async`. Ví dụ về `@Transactional`, caching và scope chỉ đóng vai trò đối chiếu cơ chế; không thay thế bài học riêng về những annotation đó.

## 2. Một đối tượng Java không tự nhiên là một bean Spring

Trong Java:

```java
ReportService service = new ReportService();
service.process();
```

Lời gọi `new`:

- Cấp phát đối tượng theo semantics của Java và chạy constructor thích hợp.
- Không tự yêu cầu `ApplicationContext` tạo/đăng ký đối tượng.
- Không tự kích hoạt `@Autowired` trên các field/setter, `BeanPostProcessor`, các callback init/destroy hay AOP proxy của Spring cho instance vừa tạo.
- Không tự đọc `@Async`, `@Transactional`, `@Cacheable` rồi thay đổi method dispatch.
- Quyền quản lý vòng đời, tài nguyên và các dependency của đối tượng thuộc code đã tạo và giữ tham chiếu đến nó.

Ngược lại, một Spring bean tồn tại nhờ **bean definition**, có thể đến từ `@Component`/`@Service` và component scan, `@Bean` trong lớp cấu hình, XML, đăng ký programmatic hoặc cơ chế auto-configuration của Spring Boot. Container chịu trách nhiệm tạo hoặc lấy object, resolve dependency, xử lý lifecycle và áp dụng bean post-processors/advice khi phù hợp.

Ví dụ về cách nhận bean qua constructor injection:

```java
@Service
public class ReportControllerFacade {
    private final ReportService reportService;

    public ReportControllerFacade(ReportService reportService) {
        this.reportService = reportService;
    }

    public void requestReport() {
        reportService.process();
    }
}
```

Đây là fragment minh họa: cần import Spring annotations và một project có bean `ReportService`. `ReportControllerFacade` phải được Spring quản lý thì Spring mới tự resolve constructor dependency. Trong Spring hiện đại, class có **một constructor** thường không cần thêm `@Autowired` vào constructor đó.

**Điều quyết định không phải từ khóa `new` có xuất hiện ở đâu trong source**, mà là object có được container **nhận làm bean**, áp dụng các bước cấu hình, và trả reference tương ứng cho caller hay không.

### 2.1. Ba trường hợp cần phân biệt

| Cách tạo/nhận | Đối tượng được Spring quản lý? | Spring có cơ hội inject/apply post-processor/proxy? |
| --- | --- | --- |
| `new ReportService()` trong method nghiệp vụ | Không, nếu không có bước đăng ký/tích hợp đặc biệt | Không tự động |
| `@Bean ReportService reportService() { return new ReportService(); }` | Có, kết quả của factory method được đăng ký là bean | Có, theo config và eligibility |
| `@Service class ReportService` và inject qua constructor | Có, khi class được scan/đăng ký | Có, theo config và eligibility |
| `context.getBean(ReportService.class)` | Có, lấy bean reference từ container | Có, nhưng có thể nhận proxy hoặc target tùy cấu hình |
| `new ReportService(dependency)` với dependency đã inject | **Object mới** không vì thế thành bean | Chỉ dependency được truyền có thể là bean; instance mới không tự được post-process |
| `ObjectProvider<ReportService>.getObject()` | Có, yêu cầu container resolve một bean | Theo scope và các post-processors có hiệu lực |

Trong ứng dụng thực, **không phải mọi bean đều được proxied**. Một bean đơn giản không có advisor phù hợp có thể được inject dưới dạng object thật. Ngược lại, khi `@Async`, `@Transactional` hoặc advisor khác đủ điều kiện, reference do container cung cấp có thể là proxy. Đừng viết “bean = proxy” như một đẳng thức tuyệt đối.

### 2.2. Sơ đồ đường đi

```text
                Tạo đối tượng thủ công
Caller ----------> new ReportService()
                      |
                      +-- gọi trực tiếp process()
                      +-- @Async chỉ là annotation metadata
                      +-- không có Spring async interceptor

                  Bean do Spring quản lý
ApplicationContext -- bean definition --> tạo target / inject / initialize
                                            |
                                            +-- BeanPostProcessor/AOP khi áp dụng
                                            |
                                            +-- proxy hoặc reference được container trả ra
                                                       |
Caller / bean khác -------- constructor injection ----+
                                                       |
                                              @Async interceptor
                                                       |
                                                TaskExecutor
                                                       |
                                                worker thread
                                                       |
                                                  target.process()
```

Sơ đồ thứ hai mô tả **trường hợp có async advice và gọi qua proxy**. Nếu cấu hình async chưa bật, method không đủ điều kiện hay caller bỏ qua proxy, interceptor sẽ không xuất hiện trên đường thực thi.

## 3. Vì sao @Async thay đổi hành vi của bean, nhưng không thay đổi một object new?

Với `@EnableAsync`, Framework đăng ký hạ tầng xử lý `@Async`. Ở chế độ mặc định `AdviceMode.PROXY`:

1. Spring nhận diện các bean/method có async advice thích hợp.
2. Khi cần, bean được expose thông qua proxy được cấu hình.
3. Caller gọi method **qua reference proxy**.
4. Interceptor chọn `Executor`/`TaskExecutor` và submit lời gọi thực tế thành task.
5. Thread worker chạy method target; caller có thể nhận `Future`/`CompletableFuture` để quan sát kết quả.

Nếu code gọi:

```java
ReportService service = new ReportService();
service.generateAsync();
```

thì `service` chỉ là object Java thường. Spring không chèn proxy vào lời gọi đó; `generateAsync()` chạy như method thông thường trên thread gọi, trừ khi **bản thân implementation** tạo thread hoặc submit một executor nào khác.

Điều này không có nghĩa mọi object thường đều luôn chạy sync; một object tự `new` vẫn có thể sử dụng `ExecutorService` hoặc `CompletableFuture.supplyAsync(...)` bằng code Java thuần. **Điểm phân biệt:** async do chính implementation quyết định khác với **async advice của Spring** qua `@Async`.

### 3.1. Ba điều kiện tối thiểu của một lời gọi @Async

- **Annotation processing đã bật:** `@EnableAsync` được nạp trong đúng Spring application context, hoặc một cấu hình tương đương.
- **Object và method đủ điều kiện:** service là Spring-managed bean và method có `@Async` ở vị trí framework nhận diện được.
- **Lời gọi đi qua advice:** thường là lời gọi từ một bean khác tới **proxy**, không phải lời gọi nội bộ `this.method()`.

Để có hệ thống tốt trong production còn cần executor được cấu hình phù hợp, xử lý lỗi, kết quả, timeout, tài nguyên và vòng đời. Có ba điều kiện trên chỉ là điểm khởi đầu, không phải chứng nhận thread-safety.

### 3.2. Đặt @Async trên method không có nghĩa Java compiler đổi method call

`@Async` là metadata được Spring xử lý qua infrastructure. Compiler Java không tự thay:

```java
service.generateAsync();
```

thành một `executor.submit(...)` bất kể `service` được tạo thế nào. Cơ chế intercept tại runtime mới tạo khác biệt. Đó là lý do unit test trực tiếp bằng `new` có thể không tái hiện behavior khi ứng dụng chạy với Spring context.

## 4. Ví dụ hoàn chỉnh Java 17+: so sánh new, getBean và constructor injection

Bài thực hành dùng **Spring Framework thuần**, không cần Spring Boot, để chứng minh rằng container/proxy mới là yếu tố quyết định.

### 4.1. Cấu trúc dự án

```text
new-vs-injected-demo/
├── pom.xml
└── src/main/java/demo/NewVsInjectedDemo.java
```

Sử dụng JDK 17+ và Maven, `spring-context` 6.2.14.

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>new-vs-injected-demo</artifactId>
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
</project>
```

Tệp `src/main/java/demo/NewVsInjectedDemo.java`:

```java
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

public class NewVsInjectedDemo {
    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {
        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setThreadNamePrefix("lesson-worker-");
            pool.setCorePoolSize(2);
            pool.setMaxPoolSize(4);
            pool.setQueueCapacity(16);
            return pool;
        }

        @Bean
        public Worker worker() {
            return new Worker(); // "new" bên trong @Bean: Spring quản lý kết quả
        }

        @Bean
        public Caller caller(Worker worker) {
            return new Caller(worker); // worker do Spring resolve
        }
    }

    public static class Worker {
        @Async("lessonExecutor")
        public CompletableFuture<String> currentThreadName() {
            return CompletableFuture.completedFuture(
                    Thread.currentThread().getName());
        }

        public CompletableFuture<String> selfInvocation() {
            return this.currentThreadName(); // Bỏ qua proxy khi gọi nội bộ
        }
    }

    public static class Caller {
        private final Worker worker;

        public Caller(Worker worker) {
            this.worker = worker;
        }

        public CompletableFuture<String> viaInjection() {
            return worker.currentThreadName();
        }
    }

    public static void main(String[] args) throws Exception {
        String callerThread = Thread.currentThread().getName();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            Worker raw = new Worker();
            Worker managed = context.getBean(Worker.class);
            Caller caller = context.getBean(Caller.class);

            String directThread = raw.currentThreadName()
                    .get(5, TimeUnit.SECONDS);
            String managedThread = managed.currentThreadName()
                    .get(5, TimeUnit.SECONDS);
            String injectedThread = caller.viaInjection()
                    .get(5, TimeUnit.SECONDS);
            String selfThread = managed.selfInvocation()
                    .get(5, TimeUnit.SECONDS);

            System.out.println("new-on-caller="
                    + directThread.equals(callerThread));
            System.out.println("managed-on-executor="
                    + managedThread.startsWith("lesson-worker-"));
            System.out.println("injected-on-executor="
                    + injectedThread.startsWith("lesson-worker-"));
            System.out.println("self-on-caller="
                    + selfThread.equals(callerThread));
            System.out.println("managed-is-proxy="
                    + AopUtils.isAopProxy(managed));
            System.out.println("distinct-object=" + (raw != managed));
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa POM:

```bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.NewVsInjectedDemo
```

Sáu dòng do `System.out.println` tạo ra, khi môi trường tải và cấu hình như ví dụ:

```text
new-on-caller=true
managed-on-executor=true
injected-on-executor=true
self-on-caller=true
managed-is-proxy=true
distinct-object=true
```

Maven có thể ghi log riêng. Kết quả kiểm tra **tên thread và proxy** chứ không phụ thuộc vào giả định worker phải chậm hơn caller.

### 4.2. Giải thích chính xác sáu kết quả

**(1) `new-on-caller=true`**

`raw = new Worker()` tự tạo object bên ngoài container. Nó có method mang `@Async` nhưng chưa được Spring bọc bằng async proxy. Do đó, method chạy trên thread caller và trả `CompletableFuture.completedFuture(...)` ngay trong lời gọi.

**(2) `managed-on-executor=true`**

`managed = context.getBean(Worker.class)` là reference được Spring cung cấp. Vì context nạp `@EnableAsync` và method public có `@Async("lessonExecutor")`, lời gọi qua reference này được intercept; phương thức target thực thi trên thread mang prefix `lesson-worker-`.

**(3) `injected-on-executor=true`**

`Caller` là bean do `@Bean` tạo, và tham số `Worker worker` trong factory method được Spring resolve. Nó nhận reference proxy thích hợp rồi gọi `worker.currentThreadName()`, nên vẫn có async advice.

**(4) `self-on-caller=true`**

`managed.selfInvocation()` không có `@Async`. Proxy chuyển lời gọi này tới target; bên trong target, `this.currentThreadName()` gọi trực tiếp method trên `this`, bỏ qua proxy; annotation ở method đích không được intercept.

**(5) `managed-is-proxy=true`**

`AopUtils.isAopProxy(managed)` kiểm tra một dấu hiệu runtime. Trong ví dụ cụ thể, async annotation làm Spring cung cấp proxy. Ở ứng dụng khác, một bean có thể **không** có proxy, hoặc proxy tồn tại vì advice khác. Kết quả `true` đơn lẻ không chứng minh tất cả lời gọi đều đi qua async interceptor.

**(6) `distinct-object=true`**

`raw` và bean do context cung cấp là hai reference khác nhau. Chúng không có lifecycle hay dependency injection chung chỉ vì cùng kiểu `Worker`.

### 4.3. Tại sao dòng return new Worker() trong @Bean lại khác?

Đây là ý quan trọng nhất:

```java
@Bean
Worker worker() {
    return new Worker();
}
```

Spring gọi factory method để **tạo bean theo bean definition**. Sau khi nhận đối tượng, container có thể inject các thuộc tính, gọi initialization callbacks và áp dụng `BeanPostProcessor` để trả ra **bean reference cuối cùng**, có thể là AOP proxy. `new` bên trong method chỉ là một bước cấp phát, không có quyền quyết định liệu object sau đó có trở thành bean hay không.

Trong khi đó:

```java
void businessMethod() {
    Worker worker = new Worker();
    worker.currentThreadName();
}
```

không có bean definition hay bean registration nào dành cho biến `worker`, nên Spring không tự intercept lời gọi đó.

Đừng kết luận “cấm dùng `new` trong Spring”. Chính Spring cũng có thể gọi constructor hoặc factory để tạo bean. Câu hỏi đúng là **container đã nhận quyền quản lý instance và reference mà caller đang giữ có phải là reference Spring cung cấp hay không?**

## 5. Constructor injection, @Autowired và đối tượng không được inject

### 5.1. Constructor injection: lựa chọn mặc định cho dependency bắt buộc

Fragment Spring (mỗi public class đặt trong file tương ứng):

```java
@Service
public class InvoiceFacade {
    private final BillingWorker worker;

    public InvoiceFacade(BillingWorker worker) {
        this.worker = worker;
    }

    public CompletableFuture<String> invoice(String id) {
        return worker.generate(id);
    }
}

@Service
public class BillingWorker {
    @Async("billingExecutor")
    public CompletableFuture<String> generate(String id) {
        return CompletableFuture.completedFuture("invoice:" + id);
    }
}
```

Giả định có `@EnableAsync`, bean `billingExecutor` và import `@Service`/`@Async`/`CompletableFuture`. Khi `InvoiceFacade` được Spring tạo, `BillingWorker` được resolve theo DI. Nếu `BillingWorker` có proxy phù hợp, field `worker` trong facade thường giữ reference proxy đó. Lời gọi từ facade sang worker đi qua async interception.

Ngược lại:

```java
public CompletableFuture<String> invoice(String id) {
    BillingWorker worker = new BillingWorker();
    return worker.generate(id);
}
```

là **fragment phản ví dụ**: service được tạo thủ công, không được Spring áp dụng proxy. Method được gọi đồng bộ nếu implementation chỉ trả `completedFuture` như ví dụ.

Một nuance: bạn *có thể* truyền một dependency được inject vào constructor của object `new` theo Java thuần. Nhưng như vậy chỉ cung cấp dependency, **không** biến object mới thành Spring bean được quản lý và proxied.

### 5.2. Tại sao @Autowired field trên object new dễ thành null?

Xét fragment:

```java
@Service
class NotificationService {
    @Autowired
    private MailGateway gateway;

    void send(String id) {
        gateway.send(id);
    }
}
```

Nếu `NotificationService` được Spring tạo và bean `MailGateway` được resolve, injection có thể thành công. Nếu code tự gọi `new NotificationService()`, `gateway` giữ giá trị mặc định `null` trừ khi bạn can thiệp thủ công; gọi `send` có thể gây `NullPointerException`.

Đó là một lý do ưu tiên constructor injection:

```java
@Service
class NotificationService {
    private final MailGateway gateway;

    NotificationService(MailGateway gateway) {
        this.gateway = gateway;
    }

    void send(String id) {
        gateway.send(id);
    }
}
```

Constructor buộc caller cung cấp dependency hợp lệ; trong ứng dụng Spring, container resolve bean `MailGateway` và truyền vào. Nếu muốn unit test bằng `new NotificationService(fakeGateway)`, điều đó hoàn toàn hợp lý: test logic Java trực tiếp, nhưng **không** nên từ test đó suy ra AOP async/transaction đã hoạt động.

### 5.3. @Autowired không thay thế @Bean hoặc component scanning

`@Autowired` là hướng dẫn **resolve dependency** khi Spring tạo/quản lý bean. Nó không tự phát hiện mọi object có field annotated trong toàn JVM.

- `@Service`/`@Component` đánh dấu class để component scanning có thể đăng ký bean.
- `@Bean` định nghĩa bean từ factory method khi lớp config được nạp.
- `@Autowired`, constructor parameters và `@Qualifier` cho biết dependency cần resolve ở injection point.
- `@EnableAsync` bật hạ tầng async; `@Async` đánh dấu nơi cần interception.

Nếu class có `@Service` nhưng nằm ngoài component scan hoặc không được import/đăng ký, annotation đó không đủ để bảo đảm có bean. Nếu class được tạo bằng `new` trong business code, có annotation cũng không tự khiến Spring quản lý object đó.

## 6. Proxy Spring: inject có thể nhận proxy, nhưng không phải lúc nào cũng vậy

### 6.1. JDK dynamic proxy và class-based proxy

Spring AOP thường sử dụng:

| Cách proxy | Nguyên tắc | Hệ quả khi inject |
| --- | --- | --- |
| JDK dynamic proxy | Proxy implement interface cần thiết | Nên inject qua interface; không nhất thiết cast được về concrete class |
| Class-based proxy (CGLIB) | Proxy tạo subclass của target class | Có thể inject qua concrete class đủ điều kiện; class/method `final` không thể được advise theo cách subclass |
| Không proxy | Không có advice áp dụng, hoặc infrastructure chưa bật | Spring vẫn có thể inject target bean bình thường, nhưng method không có interception AOP |

Loại proxy mặc định phụ thuộc cấu hình Framework/Boot, interfaces của bean, advisor và phiên bản. Không dựa cứng vào kết quả `bean.getClass() == Worker.class`: class runtime có thể là generated proxy class.

**Giới hạn quan trọng với class-based proxy:**

- Class `final` không thể bị subclass để tạo kiểu proxy này.
- Method `final` không thể được override để advise.
- Method `private` không thể được advise bởi cơ chế override.
- Method không visible thích hợp có thể có giới hạn tương tự.
- Static method không là lời gọi instance qua Spring proxy.

Hướng đi dễ kiểm chứng cho `@Async`: đặt method public trên Spring-managed service, tránh final và gọi nó thông qua bean khác.

### 6.2. Ví dụ interface injection

Fragment:

```java
public interface ExportPort {
    CompletableFuture<String> export(String id);
}

@Service
class ExportService implements ExportPort {
    @Async("exportExecutor")
    public CompletableFuture<String> export(String id) {
        return CompletableFuture.completedFuture(id);
    }
}

@Service
class ExportControllerFacade {
    private final ExportPort exportPort;

    ExportControllerFacade(ExportPort exportPort) {
        this.exportPort = exportPort;
    }

    CompletableFuture<String> run(String id) {
        return exportPort.export(id);
    }
}
```

Đây là fragment dự án Spring với các import và bean executor phù hợp; không tự chạy chỉ bằng `javac`. Inject theo `ExportPort` giúp code không phụ thuộc concrete proxy type. Nếu muốn dùng concrete-class injection, phải kiểm tra proxy strategy và tính tương thích của class, thay vì ép kiểu từ JDK proxy.

### 6.3. Làm sao biết proxy có tồn tại?

Trong một test Spring đã có bean:

```java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("exportService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(bean.getClass().getName());
```

Fragment cần `context` thích hợp. Dùng `AopUtils.isAopProxy` và thông tin bean class là bước chẩn đoán, nhưng **không** đủ khẳng định method nào đang được advise. Kiểm tra annotation, call path và tên thread/runtime result thực tế.

## 7. Phân biệt instance không được quản lý với self-invocation

Một object được tự tạo trong business code và một Spring-managed bean tự gọi method của chính nó đều có thể bỏ qua `@Async`, nhưng **đó là hai nguyên nhân độc lập**:

| Tình huống | Vì sao không có async advice? | Cách sửa |
| --- | --- | --- |
| `new ExportWorker().exportAsync(id)` trong business code | Instance này không được Spring đăng ký, post-process hoặc cung cấp qua proxy. | Inject bean `ExportWorker` hoặc lấy managed bean qua provider/factory. |
| `this.exportAsync(id)` trong target đã là Spring bean | Lời gọi nội bộ không vượt qua proxy của method cần advice. | Gọi từ bean cộng tác khác qua Spring-managed reference hoặc explicit executor. |

Ví dụ một bean đã được container quản lý vẫn mắc self-invocation:

```java
@Service
class CsvExportService {
    public void start(String id) {
        this.exportAsync(id); // Gọi thẳng trong target ở PROXY mode.
    }

    @Async("exportExecutor")
    public void exportAsync(String id) {
        // Tác vụ chạy trên executor khi được gọi qua proxy.
    }
}
```

Đoạn này là fragment Spring, cần imports, `@EnableAsync` và bean `exportExecutor`. Nếu gọi `start()` qua proxy, lời gọi `this.exportAsync()` vẫn không được chuyển thành submission mới. Thêm thread hoặc đổi scope không sửa được lỗi. Trọng tâm của bài này là **nguồn gốc và ownership của instance**, còn bài trước phân tích sâu self-call và exception semantics.

## 8. Bean scope: Spring quản lý object không có nghĩa mọi lần gọi nhận instance mới

Đừng suy từ “injected” ra “mỗi request một object” hoặc “không có shared mutable state”. Scope độc lập với sự tồn tại của proxy và với việc gọi qua `new`.

| Scope | Hành vi tổng quát | Điểm cần nhớ khi có concurrency |
| --- | --- | --- |
| `singleton` (mặc định) | Thường một instance cho mỗi bean definition trong một container | Nhiều request/worker có thể truy cập cùng state; Spring không tự khóa mutable fields |
| `prototype` | Tạo instance khi container được yêu cầu cung cấp bean | Prototype inject **một lần** vào singleton không tự đổi instance theo từng method call |
| `request` | Instance gắn request lifecycle trong web-aware context | Không nên giữ request bean/reference để xử lý background sau request |
| `session` | Instance gắn một HTTP session | Một session có thể có request đồng thời; state mutable vẫn cần kiểm soát |
| Custom scope | Do ứng dụng/container quy định | Phải hiểu lifetime, owner và thread safety cụ thể |

**Ví dụ phản trực giác:** constructor của singleton facade nhận `@Scope("prototype") Worker worker`. Worker prototype thường được resolve vào thời điểm facade tạo; facade giữ reference đó, chứ không được tạo worker mới cho mỗi lần `facade.process()`.

Nếu thật sự muốn xin bean prototype theo từng invocation, dùng `ObjectProvider<Worker>` hoặc một factory/lookup phù hợp:

```java
@Service
class TaskStarter {
    private final ObjectProvider<Worker> workers;

    TaskStarter(ObjectProvider<Worker> workers) {
        this.workers = workers;
    }

    void start() {
        Worker worker = workers.getObject();
        worker.execute();
    }
}
```

Đây là fragment, yêu cầu bean `Worker` và các imports. Với method `execute()` cần `@Async`, hãy bảo đảm bean prototype được Spring post-process/proxied phù hợp; chỉ đổi scope không giải quyết self-invocation. Việc Spring hủy bean prototype cũng có giới hạn: Spring quản lý tạo/init, nhưng container thường **không tự quản lý toàn bộ destruction callback** của các prototype đã cấp phát như đối với singleton; caller cần tự xử lý resource vòng đời dài khi cần.

### 8.1. Vì sao singleton @Async có thể gây race condition?

Một `@Service` singleton có field:

```java
@Service
class LastOrderService {
    private String lastOrderId;

    @Async("orderExecutor")
    public CompletableFuture<String> record(String id) {
        lastOrderId = id;
        return CompletableFuture.completedFuture(lastOrderId);
    }
}
```

Nếu nhiều task chạy đồng thời trên cùng singleton, `lastOrderId` là shared mutable state, có thể bị ghi đè giữa hai task. Kể cả có proxy, `@Async` không tự khiến field an toàn. Dùng immutable command/DTO, local variables và kết quả riêng cho từng invocation; nếu cần shared state, thiết kế atomicity/locking và ownership đúng nhu cầu.

Việc tạo `new LastOrderService()` cho từng request có thể vô tình làm giảm chia sẻ field trong ví dụ này, nhưng **không** phải giải pháp hợp lý để né concurrency: nó bỏ DI, AOP, lifecycle và có thể vẫn chia sẻ dependencies/static state. Sửa đúng là thiết kế state và phạm vi trách nhiệm.

## 9. @Transactional, @Cacheable và các advice khác: cùng nguyên lý, khác ý nghĩa

Sự khác biệt `new` so với injected bean không chỉ ảnh hưởng `@Async`.

| Khả năng Spring | Khi gọi qua bean/proxy phù hợp | Khi gọi trên đối tượng new thuần |
| --- | --- | --- |
| `@Async` | Interceptor có thể submit method vào executor | Không tự chuyển thread |
| `@Transactional` (proxy mode) | Interceptor có thể mở/gắn transaction theo semantics phù hợp | Annotation không tự mở transaction |
| `@Cacheable` (proxy mode) | Advice có thể kiểm tra/cache giá trị trả về | Annotation không tự cache |
| Custom `@Aspect` | Advice phù hợp có thể chạy trước/sau/xung quanh method | Không được intercept trừ khi cơ chế khác được áp dụng |
| DI `@Autowired` | Container có thể resolve dependencies | Không được inject tự động |
| Lifecycle callbacks | Có thể được chạy khi bean được khởi tạo/đóng theo điều kiện | Không tự được Spring gọi |

Đây là **mô hình proxy-based điển hình**. Một số chức năng có thể dùng AspectJ weaving hoặc một kỹ thuật khác, và Spring cung cấp những cơ chế đặc biệt để autowire/configure objects ngoài container khi ứng dụng chủ ý thiết lập. Không vì ngoại lệ nâng cao mà kết luận mọi object `new` được Spring xử lý như bean.

### 9.1. @Transactional không tự theo @Async sang thread khác

Giả sử một caller có transaction và gọi method `@Async` trên injected bean: worker thường chạy ở **thread khác**. Transaction context gắn thread caller không tự động đi theo. Nếu worker cần transaction, đặt boundary giao dịch rõ ràng ở code chạy trong worker và gọi qua proxy thích hợp. Ngoài ra, task có thể chạy sau khi transaction của caller hoàn tất.

Đừng giải thích tình huống này là “do dùng `new`” khi thực tế lỗi bắt nguồn từ **thread boundary**. Cần phân biệt:

1. Không được Spring quản lý → không có async advice.
2. Có async advice → code chạy trên worker, context giao dịch thread caller không tự chảy theo.
3. Trong worker, một lời gọi `this.transactionalMethod()` vẫn có thể bỏ qua proxy transaction nếu là self-invocation.

### 9.2. Spring không nên được dùng làm service locator ở khắp nơi

Chuyển mọi `new` thành `applicationContext.getBean(...)` trong business code thường giảm tính rõ ràng của dependency graph. Ưu tiên constructor injection với typed interfaces, và chỉ dùng `ObjectProvider`/factory khi thật sự cần lấy bean theo runtime hoặc lấy prototype nhiều lần.

## 10. Các tình huống đặc biệt với @Bean, @Configuration và new

### 10.1. Return new trong @Bean **không** phải lỗi

```java
@Configuration(proxyBeanMethods = false)
class TaskConfig {
    @Bean
    NotificationWorker notificationWorker(MailClient mailClient) {
        return new NotificationWorker(mailClient);
    }
}
```

Spring gọi method `notificationWorker(...)` và đăng ký object trả về dưới bean definition. Nó nhận constructor dependency từ container, sau đó áp dụng các bước lifecycle/post-processing thích hợp. `new` tại đây là một cách implementation factory method, không phải business code tự tạo service ngoài Spring.

### 10.2. Nhưng tự gọi phương thức @Bean không nhất thiết tạo bean được quản lý

Với cấu hình ở chế độ `proxyBeanMethods=false`, lời gọi Java trực tiếp từ một method đến một method `@Bean` khác **không** được Spring chặn để trả singleton theo bean definition. Ví dụ phản mẫu:

```java
@Configuration(proxyBeanMethods = false)
class WrongFactoryConfig {
    @Bean
    Worker worker() {
        return new Worker();
    }

    @Bean
    Caller caller() {
        return new Caller(worker()); // Gọi Java trực tiếp tới @Bean method
    }
}
```

Trong tình huống này, `Caller` có thể giữ một `Worker` được tạo trong lời gọi method trực tiếp thay vì bean reference container đã post-process/proxied. Việc `worker()` có annotation `@Bean` không biến **mọi lần gọi trực tiếp method** thành container lookup.

**Đúng hơn** là yêu cầu Spring inject tham số:

```java
@Configuration(proxyBeanMethods = false)
class GoodFactoryConfig {
    @Bean
    Worker worker() {
        return new Worker();
    }

    @Bean
    Caller caller(Worker worker) {
        return new Caller(worker);
    }
}
```

Các snippet này là fragments và giả định có lớp `Worker`, `Caller` phù hợp. Nếu dùng `@Configuration(proxyBeanMethods=true)` kiểu full configuration, Spring có cơ chế intercept một số inter-bean method calls để trả bean container; nhưng phụ thuộc vào cơ chế enhancement và cách viết code. **Constructor/method parameter injection** vẫn rõ ràng hơn, nhất là khi đưa class sang chế độ lite/proxyBeanMethods=false.

### 10.3. @ComponentScan không biến đối tượng đã tạo thành bean

`@ComponentScan` tìm class để đăng ký bean definitions. Nếu trong method bạn viết `new ComponentClass()`, đối tượng riêng đó không được “nhặt” vào container sau khi scan, dù cùng class với một bean đã đăng ký.

### 10.4. Prototype bean và đối tượng new không đồng nghĩa

Cả prototype lookup và `new` đều có thể sinh instance mới, nhưng khác nhau ở việc **prototype vẫn được container tạo và post-process**, còn `new` thuần không. Nếu worker cần proxy/lifecycle thì xin prototype từ container, không dùng `new` thay thế một cách tùy tiện.

## 11. Spring Boot không tự sửa đường gọi sai

Spring Boot thêm auto-configuration và convention, nhưng không làm thay đổi nguyên tắc container/proxy của Spring Framework:

- `@SpringBootApplication` thường kích hoạt component scanning và auto-configuration trong phạm vi phù hợp; class nằm ngoài scan có thể không được đăng ký.
- Boot có thể tạo executor theo điều kiện, nhưng vẫn cần bật `@EnableAsync` để annotation processing chạy trong cấu hình thông thường.
- Có bean executor không làm cho `new Worker()` trở thành managed bean.
- Có `@EnableAsync` không làm self-invocation `this.work()` qua proxy.
- Có `@Service` trên class nhưng code gọi trực tiếp `new Service()` vẫn là một instance riêng ngoài container.

Ví dụ fragment Boot:

```java
@SpringBootApplication
@EnableAsync
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}

@Service
class DocumentWorker {
    @Async("documentExecutor")
    public CompletableFuture<String> parse(String id) {
        return CompletableFuture.completedFuture("parsed:" + id);
    }
}

@Service
class DocumentFacade {
    private final DocumentWorker worker;

    DocumentFacade(DocumentWorker worker) {
        this.worker = worker;
    }

    CompletableFuture<String> request(String id) {
        return worker.parse(id);
    }
}
```

Đây là ví dụ cấu trúc, **chưa phải chương trình độc lập**, vì cần định nghĩa bean `documentExecutor`, imports và project Spring Boot. Nó minh họa đường gọi `DocumentFacade → injected DocumentWorker → proxy async`. Nếu thay `worker` bằng `new DocumentWorker()`, code cùng tên method không còn được Spring `@Async` intercept.

Để biết pool nào thực thi, xem `@Async("documentExecutor")`, loại bean `Executor`, tình trạng Spring context và thread name. Không giả định một bean custom sẽ tự nhận `spring.task.execution.*` properties của Boot.

## 12. Khi nào dùng new là đúng?

Dùng `new` rất bình thường cho **value objects, DTOs, collections, domain models và các thuật toán thuần Java**, khi bạn **không cần** container quản lý đối tượng đó:

```java
record ExportCommand(String requestId, String path) {}

ExportCommand command =
        new ExportCommand("R-123", "/reports/summary.csv");
List<String> lines = new ArrayList<>();
```

Đây là fragment với import Java cần thiết. Những object dữ liệu ngắn hạn này không tự động cần `@Component` hay `@Service`. Việc inject mọi DTO vào Spring container thường làm khó quản lý identity, state và scope.

**Nên inject Spring bean** khi đối tượng:

- Chứa business service được chia sẻ, có nhiều dependencies cần DI.
- Cần AOP advice như `@Async`, `@Transactional`, `@Cacheable`.
- Có tài nguyên cần lifecycle container (executor, datasource, client với cấu hình, scheduler).
- Cần được cấu hình tập trung, thay thế implementation qua interface, quản lý scope hoặc tích hợp metrics.
- Cần thống nhất ownership và test integration với Spring.

**Không cần inject** chỉ vì “có class Java”. Một object thuần có thể được tạo bằng `new` bên trong Spring-managed service; Spring service vẫn là bean, trong khi DTO mà nó tạo vẫn là object bình thường. Đó là thiết kế hoàn toàn hợp lệ.

### 12.1. Nhà máy (factory) tạo domain object có thể là bean

Bạn có thể inject một factory bean có dependency/configuration, còn object factory tạo ra vẫn là domain object bình thường:

```java
@Component
class ExportCommandFactory {
    ExportCommand create(String id, String path) {
        return new ExportCommand(id, path);
    }
}
```

Fragment này cho thấy không phải mọi object do bean tạo ra đều trở thành bean. **Spring quản lý factory**, không mặc nhiên quản lý từng `ExportCommand`.

## 13. Kiểm chứng bằng test: unit test khác integration test

### 13.1. Unit test cho logic Java

Nếu bạn tạo service bằng `new` và tự truyền mock/fake dependency, bạn đang test method logic. Đây là test hợp lệ, nhanh và dễ kiểm soát. Nhưng một assertion thành công ở unit test ấy **không chứng minh `@Async`, transaction advice hay bean lifecycle có hiệu lực**, vì không có container/proxy tương ứng.

Ví dụ với method thuần:

```java
var worker = new BillingWorker();
var result = worker.generate("INV-1").join();

// Kiểm tra logic result, không kiểm tra Spring async advice.
assertEquals("invoice:INV-1", result);
```

Đây là fragment JUnit, giả định `BillingWorker` đủ điều kiện khởi tạo bằng no-arg constructor như ví dụ trước và đã import JUnit. Nếu worker cần dependency bắt buộc, cung cấp fake/mock bằng constructor thay vì bỏ qua hợp đồng object.

### 13.2. Integration test phải dùng Spring context

Với test xác minh AOP:

1. Nạp config có `@EnableAsync` và bean executor.
2. Inject service từ Spring; đừng `new` nó trong test.
3. Xác định reference nhận được có proxy khi bạn kỳ vọng advice.
4. Gọi method qua bean từ context/bean khác.
5. Kiểm tra thread name của target, future result, exception, timeout.
6. Tạo một đối tượng `new` để làm nhóm đối chứng, chứng minh đường chạy khác nhau.
7. Kiểm tra self-invocation: method bên trong target chạy trên caller dù bean bên ngoài được inject.
8. Đóng context để xác nhận lifecycle executor và dừng tài nguyên đúng thời hạn.

### 13.3. Tránh test timing bằng Thread.sleep

Dùng `CountDownLatch` để điều phối sự kiện thay vì dùng `Thread.sleep(50)` rồi hy vọng worker chưa kịp chạy:

```java
// Fragment minh họa ở bên trong @Async method được gọi qua proxy:
started.countDown();
release.await();
return CompletableFuture.completedFuture("finished");
```

Caller có thể đợi `started.await(timeout, unit)`, xác minh task chưa hoàn thành, sau đó `release.countDown()` và đợi future. Cần xử lý `InterruptedException`, đặt timeout để test không treo và bảo đảm giải phóng latch ở `finally`.

Một test stress có thể hỗ trợ phát hiện race, nhưng **không** thay thế việc hiểu bean scope, state ownership và thread boundary.

## 14. Debug một method @Async “không chạy async”

Lần lượt trả lời, đừng sửa pool theo cảm tính:

1. **Instance đến từ đâu?** Lần theo `new`, `@Bean`, `@Service`, constructor injection, `getBean` hoặc factory.
2. **Context có quản lý instance không?** Có bean definition thực và object được Spring cung cấp không? Object bị tạo lại thủ công ở đâu?
3. **Bean có proxy không?** Kiểm tra `AopUtils.isAopProxy(...)` và loại proxy (JDK/interface hoặc class-based) khi phù hợp.
4. **Async infrastructure đã bật chưa?** `@EnableAsync` có được load trong đúng context?
5. **Method có eligible không?** `@Async` ở method/class nào; method public/non-final? Return type `void`/`Future`/`CompletableFuture`?
6. **Lời gọi qua reference nào?** Reference từ DI/proxy hay `this`? Có reflection, private helper hay tự tạo object không?
7. **Executor nào được chọn?** `@Async("...")`, `AsyncConfigurer`, default resolver, bean name, prefix.
8. **Task có bị reject hoặc dừng không?** Pool/queue có hữu hạn? Executor có còn sống không?
9. **Task thực tế chạy trên thread nào?** In caller và worker thread names; không chỉ suy từ có `CompletableFuture`.
10. **Nếu Spring Boot:** bean nào do Boot auto-configure, bean nào do bạn khai báo; property có bind vào đúng executor không?
11. **Nếu vấn đề là dữ liệu sai:** kiểm tra singleton shared mutable state, context propagation, transaction boundaries, chứ không chỉ proxy.
12. **Nếu vấn đề là shutdown:** xem owner executor, task đang chờ và chiến lược graceful stop.

Một bảng nhanh:

| Triệu chứng | Nguyên nhân khả dĩ | Cách xác minh |
| --- | --- | --- |
| Tạo service bằng `new` rồi `@Async` chạy sync | Không có Spring interception | So sánh với bean inject, kiểm tra thread |
| Method async chạy sync trong cùng bean | Self-invocation | Vẽ call graph, tách bean rồi test lại |
| `@Autowired` field là null | Instance được tạo ngoài container | Tìm điểm `new`; dùng constructor injection |
| `@Transactional` không mở transaction | Không qua proxy hoặc thiếu infrastructure | Xác minh bean, advice và call path |
| Inject bean theo class bị lỗi | JDK dynamic proxy chỉ expose interface | Inject interface, kiểm tra proxy strategy |
| Bean inject được nhưng không có proxy | Advisor không áp dụng hoặc infrastructure chưa bật | `AopUtils`, annotations, condition/config |
| `@Async("pool")` không tìm executor | Bean name/qualifier sai hoặc bean chưa được đăng ký | Liệt kê bean Executor trong context |
| Unit test qua `new` pass nhưng runtime khác | Unit test bypass AOP/lifecycle | Có integration test Spring context |
| Một request nhìn thấy dữ liệu request khác | Mutable field trong singleton/shared dependency | Đổi state sang local/immutable hoặc đồng bộ đúng |
| Tăng số thread vẫn không nhanh | Queue/backpressure/downstream bottleneck | Metric active/queue/rejection/latency |

## 15. Bài tập tích hợp: xác định ai đang quản lý từng object

### Bài 1: phân loại sáu reference

Cho các fragment sau trong ứng dụng đã bật `@EnableAsync`:

```java
Worker a = new Worker();
Worker b = context.getBean(Worker.class);
Worker c = injectedWorker;
Worker d = factory.createWorker();
Worker e = provider.getObject();
Worker f = new Worker(injectedDependency);
```

Với mỗi biến, hãy ghi: **nguồn tạo**, **container-managed?**, **có thể là proxy?**, **có được áp dụng `@Async` nếu method được gọi qua reference đó?**, **ai quản lý lifecycle?**. Với `d`, không đoán: phải đọc implementation của factory và xem nó dùng `new` hay Spring container. Với `e`, phải biết `ObjectProvider` lấy bean nào và bean scope là gì. Với `f`, việc dependency là bean không khiến `f` tự thành bean.

### Bài 2: sửa lỗi bypass proxy

Refactor:

```java
@Service
class ExportFacade {
    public void start(String id) {
        ExportWorker worker = new ExportWorker();
        worker.exportAsync(id);
    }
}
```

thành một facade constructor-inject `ExportWorker` và gọi `worker.exportAsync(id)`; bật `@EnableAsync` và có bean executor. Giải thích vì sao thay đổi này **chỉ** giải quyết một vấn đề: vẫn cần kiểm tra invocation thực qua proxy, result/error và thread-safety.

### Bài 3: self-invocation

Thêm method `startInternal()` vào `ExportWorker` và cho nó gọi `this.exportAsync(id)`. Ghi lại thread chạy. Tách `startInternal()` vào bean facade khác và lặp lại. So sánh tại sao cả hai lần đều dùng bean được Spring tạo nhưng chỉ lời gọi từ facade mới qua proxy.

### Bài 4: @Bean với new

Viết hai phiên bản cấu hình:

1. `@Bean Worker worker() { return new Worker(); }`, rồi `@Bean Caller caller(Worker worker) { return new Caller(worker); }`.
2. Với `proxyBeanMethods=false`, `@Bean Caller caller() { return new Caller(worker()); }`.

Quan sát đối tượng được inject, proxy và hành vi `@Async`. Giải thích vì sao factory method chỉ nên lấy bean dependency qua tham số để tránh bypass container.

### Bài 5: đồng thời và scope

Tạo một singleton `@Service` có mutable field `lastRequestId`, hai lời gọi `@Async` ghi field khác giá trị, rồi dùng latch điều phối để chứng minh kết quả có thể bị trộn. Sửa theo hướng stateless/immutable input, không chỉ thay bằng `new` hoặc `prototype`. Làm rõ ai sở hữu trạng thái và thời điểm kết thúc request.

### Bài 6: kiểm thử đối chứng

Tạo một unit test dùng `new Worker()` và một integration test nạp Spring context. Mỗi test kiểm tra output nghiệp vụ; integration test kiểm tra thêm `AopUtils.isAopProxy` và thread prefix khi gọi qua bean. Giải thích vì sao unit test không phải bằng chứng về async advice.

## 16. Checklist kiến thức trước khi chuyển sang bài tiếp theo

- [ ] Tôi giải thích được vì sao `new Service()` ngoài container không tự nhận Spring DI/AOP.
- [ ] Tôi phân biệt được `new` trong method `@Bean` với `new` trong business method.
- [ ] Tôi biết `@Service` chỉ dẫn đến bean khi class thực sự được scan/đăng ký.
- [ ] Tôi biết constructor injection cung cấp bean reference, có thể là Spring AOP proxy.
- [ ] Tôi biết một injected bean không phải lúc nào cũng có proxy, và proxy không đồng nghĩa với instance mới theo mỗi lời gọi.
- [ ] Tôi giải thích được điều kiện `@EnableAsync` + `@Async` + invocation qua proxy.
- [ ] Tôi phân biệt được đối tượng tự tạo và self-invocation: hai nguyên nhân khác nhau dẫn đến bỏ qua advice.
- [ ] Tôi hiểu giới hạn của JDK interface proxy, class-based proxy và final/private method.
- [ ] Tôi có thể kiểm chứng bằng `ApplicationContext`, `AopUtils`, thread name và future.
- [ ] Tôi biết async advice không tự sửa race condition, transaction context hoặc shared mutable state.
- [ ] Tôi chọn `new` cho DTO/value object khi phù hợp, inject service/resource cần Spring quản lý.
- [ ] Tôi biết prototype bean vẫn khác instance `new` và không tự thay đổi theo mỗi lần gọi từ singleton.
- [ ] Tôi không dùng Spring Boot auto-configuration làm lý do bỏ qua đường đi proxy.
- [ ] Tôi có test Spring integration riêng để bảo đảm concurrency behavior được cấu hình đúng.

**Kết luận:** `new` là cách Java tạo object; **DI là cách Spring cung cấp bean reference từ container**. Sự khác biệt quan trọng nhất khi học Spring concurrency là **lời gọi chạy trên object nào, reference đó có đi qua proxy hay không, và executor nào thực sự nhận task**. Khi mô tả chính xác đường đi từ caller → injected proxy → interceptor → executor → target, bạn có thể giải thích vì sao `@Async` có hoặc không có hiệu lực, đồng thời tránh nhầm lẫn giữa bean scope, lifecycle và thread-safety.

## 17. Tài liệu chính thức để tra cứu

- Spring Framework — [Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html): container tạo/resolve dependencies và constructor injection.
- Spring Framework — [Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): bean definition và quản lý object.
- Spring Framework — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK proxy, class-based proxy và self-invocation.
- Spring Framework — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableAsync`, `@Async`, executor qualification và exception handling.
- Spring Framework — [Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype và vòng đời.
- Spring Framework Javadoc — [@Bean](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Bean.html): factory method tạo managed bean.
- Spring Framework Javadoc — [@EnableAsync](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): proxy advice mode và cấu hình async.

Các chi tiết proxy mặc định và auto-configuration có thể thay đổi theo release. Khi triển khai, hãy đối chiếu **đúng phiên bản Spring Framework/Spring Boot của dự án** thay vì suy luận từ một ví dụ duy nhất.
