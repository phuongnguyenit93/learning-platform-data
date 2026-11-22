# Nhận diện chế độ AspectJ và yêu cầu weaving khi cần lựa chọn khác

Trong Spring Framework, `@Async` thường hoạt động thông qua **Spring AOP proxy**. Khi một bean khác gọi method được đánh dấu `@Async` **qua proxy**, advice chuyển công việc sang executor; nhưng khi một method trong cùng bean gọi `this.asyncMethod()`, lời gọi nội bộ không đi qua proxy nên advice không được kích hoạt. Đây là giới hạn quan trọng của `AdviceMode.PROXY`.

Spring còn hỗ trợ **`@EnableAsync(mode = AdviceMode.ASPECTJ)`**. Ở chế độ này, advice của `@Async` không chỉ nằm ở đối tượng proxy; AspectJ có thể can thiệp tại **method execution join point** sau khi mã ứng dụng **đã được weave**. Nhờ đó, self-invocation có thể được chặn. Nhưng chỉ đổi enum `mode` là chưa đủ: cần có module `spring-aspects`, cơ chế compile-time/load-time weaving thực sự, cùng kiểm thử để xác nhận bytecode của lớp cần thiết đã được xử lý.

Bài học thuộc nhóm **Proxy và lời gọi**, tập trung vào cách **nhận diện khi nào cần lựa chọn AspectJ**, phụ thuộc kỹ thuật và giới hạn thực tế, không mặc định rằng mọi ứng dụng Spring đều cần weaving.

## 1. Mục tiêu học tập

Sau bài này, bạn sẽ có thể:

- Giải thích `AdviceMode.PROXY` mặc định và vì sao `this.method()` không kích hoạt advice của Spring AOP proxy.
- Phân biệt JDK dynamic proxy, class-based proxy và AspectJ bytecode weaving.
- Mô tả `AdviceMode.ASPECTJ`, sự khác biệt khi advice được gắn vào method execution, và lý do self-invocation có thể hoạt động.
- Biết các điều kiện tối thiểu: `@EnableAsync(mode=AdviceMode.ASPECTJ)`, `spring-aspects`, compiler/weaver tương thích và lớp đích thật sự được weave.
- Phân biệt compile-time weaving (CTW), post-compile weaving và load-time weaving (LTW).
- Biết rằng `@EnableAspectJAutoProxy`, `proxyTargetClass=true` hoặc chỉ thêm dependency **không tương đương** với weaving.
- Xây dựng ví dụ và test không dùng `Thread.sleep`, nhận diện luồng chạy và thời điểm hoàn tất.
- Cân nhắc refactor thành bean riêng hoặc dùng `TaskExecutor` trực tiếp trước khi tăng độ phức tạp của build/deployment.

## 2. Cơ chế @Async với Spring proxy

Trong cấu hình thường gặp:

~~~java
@Configuration
@EnableAsync
public class AppAsyncConfig {
}
~~~

Đây là **đoạn cấu hình Spring** (cần import `Configuration` và `EnableAsync`), không phải chương trình Java chạy độc lập. `@EnableAsync` không ghi `mode` có nghĩa là dùng **`AdviceMode.PROXY`**, cơ chế mặc định của Spring.

Luồng thực thi khi một component gọi bean khác:

~~~text
Caller (thread A)
       |
       v
Spring-managed reference -> proxy
       |
       +-- @Async interceptor
               |
               +-- submit work -> TaskExecutor
                       |
                       +-- worker thread B chạy target method
~~~

Thực tế còn phụ thuộc executor: `SyncTaskExecutor` chạy trên caller, `CallerRunsPolicy` có thể chạy trên caller khi pool bão hòa. Vì vậy ngay cả khi advice đã intercept, không nên hứa luôn có thread vật lý khác.

### Self-invocation: vì sao method gọi chính nó lại bỏ qua proxy?

~~~text
Caller -> proxy -> target.outer()
                        |
                        +-- this.innerAsync()
                                   |
                                   +-- trực tiếp target.innerAsync()
                                       KHÔNG qua proxy
~~~

Trong Java, lời gọi `this.innerAsync()` nằm trong đối tượng đích. Spring proxy không được gọi lại nên `@Async` trên `innerAsync` không có cơ hội tác động ở đường gọi đó.

Ví dụ:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ExportService {
    public CompletableFuture<String> begin(String exportId) {
        return perform(exportId); // self-invocation
    }

    @Async("exportExecutor")
    public CompletableFuture<String> perform(String exportId) {
        return CompletableFuture.completedFuture("done:" + exportId);
    }
}
~~~

Đây là **Spring service**, không phải file chạy độc lập vì cần Spring context. Nếu một bean khác gọi `exportService.perform("A")` qua proxy, advice có thể chuyển phần body sang executor. Nếu bean khác gọi `exportService.begin("B")`, method `begin` tự gọi `perform`; trong PROXY mode, body `perform` chạy trực tiếp trên thread của `begin`.

Do body quá nhanh, `CompletableFuture.isDone()` có thể là `true` trong cả hai đường; **không dùng trạng thái ngay sau lời gọi làm test duy nhất**. Hãy giữ body bằng latch hoặc ghi thread identity khi kiểm chứng.

## 3. JDK proxy, CGLIB proxy và AspectJ là ba khái niệm khác nhau

| Thành phần | Vai trò | Có chữa self-invocation của @Async không? |
| --- | --- | --- |
| JDK dynamic proxy | Proxy dựa trên interface | Không: self-call vẫn bỏ qua proxy |
| Class-based proxy (thường CGLIB) | Proxy dựa trên subclass | Không tự giải quyết self-call bên trong target |
| AspectJ weaving | Biến đổi bytecode của class, gắn advice vào join point | Có thể: khi method đã weave và khớp pointcut |
| `@EnableAspectJAutoProxy` | Bật Spring AOP dùng cú pháp `@AspectJ` | **Không đủ** để tạo AspectJ bytecode weaving |
| `@EnableAsync(mode=AdviceMode.ASPECTJ)` | Chọn AspectJ advice mode cho async | **Chưa đủ** nếu thiếu compiler/weaver và aspect |

`proxyTargetClass=true` có ý nghĩa khi Spring đang **dùng proxy mode**: chọn proxy dạng subclass thay cho interface proxy khi thích hợp. Với `AdviceMode.ASPECTJ`, Spring ghi rõ `proxyTargetClass` **bị bỏ qua** đối với advice async. Tham số đó không thể thay thế việc weave.

Tương tự, `@EnableAspectJAutoProxy` dễ gây hiểu nhầm vì có chữ “AspectJ”, nhưng hạ tầng đó chủ yếu sử dụng **Spring AOP proxy-based** để thực thi advice được viết bằng cú pháp `@Aspect`. Nó không biến mọi class thành class đã được AspectJ compiler/weaver sửa bytecode.

## 4. AspectJ mode can thiệp như thế nào?

`@EnableAsync(mode = AdviceMode.ASPECTJ)` chọn cơ chế sử dụng aspect `org.springframework.scheduling.aspectj.AnnotationAsyncExecutionAspect` thuộc module `spring-aspects`. Khi weaving đã thực sự áp vào class đích, advice can thiệp tại method execution join point. Lời gọi ngoài hoặc trong object đều dẫn đến execution join point đã được weave.

~~~text
Caller -> gọi WorkService.outer()
                    |
                    +-- this.innerAsync()
                               |
                               +-- EXECUTION join point đã weave
                                      |
                                      +-- async advice / executor
                                             |
                                             +-- worker chạy body
~~~

Điều này khác cơ bản với một Spring proxy chỉ chặn lời gọi **đi qua proxy reference**. Vì thế AspectJ mode là một giải pháp được Spring tài liệu nêu ra cho những trường hợp cần interception nâng cao, chẳng hạn self-invocation.

Nhưng còn các điều kiện bắt buộc:

- `@Async` phải có chữ ký được hỗ trợ: `void` hoặc một kiểu `Future` phù hợp, bao gồm `CompletableFuture`.
- Annotation và điểm method execution phải khớp pointcut mà `AnnotationAsyncExecutionAspect` hỗ trợ.
- Lớp chứa method phải thực sự được weave, không chỉ được Spring component-scan.
- Aspect cần khả năng tìm executor và/hoặc được Spring cấu hình phù hợp.
- Executor phải còn nhận việc; overload, shutdown và lỗi trong tác vụ vẫn có thể xảy ra.
- `@Async` không được hỗ trợ trên method khai báo bên trong lớp `@Configuration` theo hợp đồng annotation của Spring.

**Không suy diễn:** AspectJ không làm mọi constructor, mọi callback vòng đời hoặc bất kỳ method Java nào trở thành async. Nó chỉ thêm advice tại các join point được weave và khớp định nghĩa aspect. Spring còn cảnh báo không kết hợp `@Async` trực tiếp với lifecycle callback như `@PostConstruct`.

## 5. Weaving là gì, và vì sao không thể bỏ qua?

**Weaving** là quá trình gắn các aspect/advice vào bytecode của lớp đích. Với Spring `@Async` ở AspectJ mode, chỉ tải `spring-aspects.jar` lên classpath **không đủ**: cần có công cụ thực thi weaving để thay đổi class file được JVM chạy.

Có ba giai đoạn đáng biết:

| Cơ chế | Khi nào weave? | Ưu điểm | Lưu ý |
| --- | --- | --- | --- |
| Compile-time weaving (CTW) | Khi build/biên dịch bằng AspectJ compiler `ajc` | Artifact được weave cố định, dễ kiểm soát trước deploy | Build tool và compiler phải hỗ trợ Java bytecode version |
| Post-compile/binary weaving | Sau khi `javac` tạo class, dùng `ajc` trên class/JAR | Có thể tách bước weave ra khỏi compile thông thường | Phải đảm bảo artifact cuối chính là bản woven |
| Load-time weaving (LTW) | Khi JVM nạp class, qua agent/transformer | Không cần tạo class woven ở build nếu runtime hỗ trợ | Classloader, startup, thời điểm load và deployment phức tạp hơn |

### CTW: weave ở quá trình build

~~~text
Source Java + annotation + Spring aspects
                  |
                  v
          AspectJ compiler / ajc
                  |
                  v
        Class đã được weave
                  |
                  v
        Đóng gói, deploy, chạy
~~~

`javac` bình thường **không** thực thi AspectJ weaving. Nếu dự án chỉ chạy Maven compiler plugin Java thông thường, `@EnableAsync(mode=ASPECTJ)` sẽ không tự làm file `.class` thay đổi. Muốn CTW, cần cấu hình `ajc`/AspectJ build plugin cùng aspect path và weave target phù hợp.

Ưu điểm của CTW là có thể xác minh file `.class` trong artifact cuối trước khi deploy. Đổi lại, pipeline phải bảo đảm compiler AspectJ đọc được source/class target đang dùng; đặc biệt khi nâng phiên bản Java, phải kiểm tra compatibility của `ajc`.

### LTW: weave khi JVM nạp class

~~~text
JVM startup
   |
   +-- AspectJ weaver/agent có hiệu lực
   |
   +-- phát hiện META-INF/aop.xml và định nghĩa aspect
   |
   +-- classloader nạp com.example.ExportService
                 |
                 +-- biến đổi bytecode tại thời điểm load
                 |
                 +-- JVM định nghĩa class đã weave
~~~

Nếu class cần weave đã được nạp **trước** lúc weaver hoạt động, việc bật annotation hoặc thêm agent sau đó không tự bảo đảm class sẽ được sửa lại. Thông thường phải khởi động JVM đúng cấu hình ngay từ đầu, hoặc dùng giải pháp instrumentation/retransformation phù hợp được hỗ trợ và kiểm chứng riêng.

Một đường LTW phổ biến dùng AspectJ Java agent:

~~~bash
java -javaagent:/opt/app/lib/aspectjweaver.jar -jar app.jar
~~~

Đây là **lệnh mẫu cho hệ đã có aspectjweaver.jar ở đường dẫn đó**, không phải lệnh cài đặt tự động. Tham số `-javaagent` là **JVM option** và phải đứng trước `-jar`. `spring-aspects` cần có trong runtime classpath ứng dụng; classloader phải nhìn thấy cả aspect lẫn class được weave.

Spring cũng có `@EnableLoadTimeWeaving` và cơ chế `LoadTimeWeaver` theo classloader; trong một số môi trường có thể sử dụng `spring-instrument.jar` để cung cấp instrumentation. Cần phân biệt Spring instrumentation agent với AspectJ weaver, và không khẳng định chỉ thêm `@EnableLoadTimeWeaving` là mọi `@Async` AspectJ đã hoạt động.

## 6. Các thành phần phải có khi chọn ASPECTJ

Bốn điều kiện cần phối hợp:

1. **Chế độ advice:** cấu hình `@EnableAsync(mode = AdviceMode.ASPECTJ)` trong Spring ApplicationContext thích hợp.
2. **Spring aspect:** module `org.springframework:spring-aspects`, chứa `AnnotationAsyncExecutionAspect` và metadata aspect.
3. **Công cụ weaving:** AspectJ compiler `ajc` ở CTW hoặc AspectJ weaver/agent tương thích ở LTW; weaving phải áp **đúng class đích**.
4. **Executor/configuration/test:** executor được resolve, class không bị load quá sớm, aspect thực sự can thiệp, và test xác nhận đường self-call hoạt động.

Ví dụ dependency Maven, **chỉ là fragment bên trong `<dependencies>` của dự án có Spring Boot BOM/parent quản lý phiên bản**:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-aspects</artifactId>
</dependency>
<dependency>
    <groupId>org.aspectj</groupId>
    <artifactId>aspectjweaver</artifactId>
</dependency>
~~~

Nếu không có dependency management, mỗi dependency cần version tương thích với Spring và JDK của dự án. Với CTW, cần thêm build plugin/compiler AspectJ và cấu hình weave; chỉ thêm hai dependency chưa thay thế được bước đó.

`spring-aspects.jar` phát hành `META-INF/aop.xml` để đăng ký những Spring aspect phổ biến, trong đó có `AnnotationAsyncExecutionAspect`. Với LTW, AspectJ thường đọc metadata `META-INF/aop.xml` trên runtime classpath. Nếu tự đặt file cấu hình với include/exclude, phải đảm bảo lớp của mình **không bị loại khỏi phạm vi weave** và không đăng ký aspect trùng lặp một cách tùy tiện.

## 7. Ví dụ Spring sử dụng PROXY mode mặc định

Tệp **DefaultAsyncConfig.java**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class DefaultAsyncConfig {

    @Bean(name = "exportExecutor")
    public ThreadPoolTaskExecutor exportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("export-");
        return executor;
    }
}
~~~

Tệp **ExportService.java** (như ví dụ trước):

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ExportService {
    public CompletableFuture<String> begin(String exportId) {
        return perform(exportId);
    }

    @Async("exportExecutor")
    public CompletableFuture<String> perform(String exportId) {
        return CompletableFuture.completedFuture("done:" + exportId);
    }
}
~~~

Đây là **hai class của một ứng dụng Spring**, cần Spring context và thư viện; không chạy đơn lẻ bằng `java ExportService`. Không gọi `initialize()` lặp lại trên executor do container đang quản lý.

Kết quả về mặt đường chạy:

| Lời gọi từ bean khác | PROXY mode |
| --- | --- |
| `exportService.perform("A")` | Gọi qua proxy, async advice có thể gửi task tới `exportExecutor` |
| `exportService.begin("B")` | `begin` chạy và tự gọi `perform` trên target; phần `@Async` không được chặn qua proxy |

Ở ví dụ này, Future có thể hoàn thành rất nhanh nên không đo đường chạy bằng `future.isDone()` tức thì; hãy ghi thread identity hoặc thêm một latch có thời gian chờ kiểm soát.

### Phương án thường tốt hơn: tách bean

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class ExportStarter {
    private final ExportWorker worker;

    public ExportStarter(ExportWorker worker) {
        this.worker = worker;
    }

    public CompletableFuture<String> begin(String exportId) {
        return worker.perform(exportId);
    }
}
~~~

Tệp **ExportWorker.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ExportWorker {
    @Async("exportExecutor")
    public CompletableFuture<String> perform(String exportId) {
        return CompletableFuture.completedFuture("done:" + exportId);
    }
}
~~~

Đây là **hai class trong các tệp riêng** với thư viện Spring. Bean `ExportStarter` inject `ExportWorker` đã được Spring quản lý, nên lời gọi `worker.perform(...)` đi qua reference proxy của bean, thay vì self-invocation. Nếu vấn đề chỉ có một method nội bộ, refactor này thường đơn giản, minh bạch hơn và tránh đưa AspectJ weaving vào build/deploy.

Một lựa chọn khác là gửi `Runnable` hoặc `Callable` trực tiếp qua `TaskExecutor` tại nơi muốn chuyển thread; lúc đó không phụ thuộc interception của proxy, nhưng phải chủ động quản lý Future, exception và lifecycle.

## 8. Cấu hình thay thế: ASPECTJ mode

Khi việc refactor không phù hợp và thực sự cần interception bên trong class, cấu hình có thể là:

Tệp **AspectJAsyncConfig.java**:

~~~java
import org.springframework.context.annotation.AdviceMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync(mode = AdviceMode.ASPECTJ)
public class AspectJAsyncConfig {

    @Bean(name = "exportExecutor")
    public ThreadPoolTaskExecutor exportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("export-");
        return executor;
    }
}
~~~

Chỉ chọn **một cấu hình `@EnableAsync` phù hợp** trong ApplicationContext cho kịch bản thử nghiệm; không nạp song song hai class config mẫu như hai cấu hình cạnh tranh. `@EnableAsync(mode=ASPECTJ)` có ý nghĩa sau khi đã có **Spring aspect + weaving thực sự**. Nếu `ExportService` đã được weave, `begin("B")` có thể dẫn đến advice ở execution của `perform` mặc dù gọi trong cùng bean.

Không có proxy **cho phần async interception theo AspectJ mode**, nhưng các tính năng Spring AOP khác vẫn có thể tạo proxy độc lập. Bật AspectJ cho `@Async` không có nghĩa `@Transactional` hoặc toàn bộ các advice khác cũng tự chuyển sang AspectJ mode.

Tương tự, cấu hình:

~~~java
@EnableAsync(mode = AdviceMode.ASPECTJ, proxyTargetClass = true)
~~~

là **một fragment annotation**; `proxyTargetClass` bị bỏ qua cho AspectJ mode, không tạo ra “weaving mạnh hơn”. Muốn xác minh AspectJ, hãy kiểm tra build agent, weave info và kết quả integration test, không dựa vào một flag proxy.

## 9. Ví dụ Java 17+ độc lập: self-call vượt qua wrapper

Ví dụ này minh họa **nguyên lý đường gọi proxy bằng một wrapper Java thuần**, không phụ thuộc Spring/AspectJ. Wrapper gửi `work()` qua executor nếu caller gọi qua nó, nhưng `Target.entry()` tự gọi `work()` trên `this` nên bỏ qua wrapper. Đây không phải cài đặt Spring AOP đầy đủ; nó chỉ minh họa vì sao self-invocation có kết quả khác.

Tệp **ProxyBoundaryDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class ProxyBoundaryDemo {
    interface WorkPort {
        void entry();
        void work();
    }

    static final class Target implements WorkPort {
        final CountDownLatch done = new CountDownLatch(1);
        final AtomicReference<Thread> executedBy = new AtomicReference<>();

        @Override
        public void entry() {
            work(); // this.work(), không đi qua wrapper
        }

        @Override
        public void work() {
            executedBy.set(Thread.currentThread());
            done.countDown();
        }
    }

    static final class DispatchWrapper implements WorkPort {
        private final Target target;
        private final ExecutorService executor;

        DispatchWrapper(Target target, ExecutorService executor) {
            this.target = target;
            this.executor = executor;
        }

        @Override
        public void entry() {
            target.entry();
        }

        @Override
        public void work() {
            executor.execute(target::work);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        Thread caller = Thread.currentThread();

        try {
            Target first = new Target();
            WorkPort wrapper1 = new DispatchWrapper(first, executor);

            wrapper1.work(); // đi qua wrapper -> executor
            if (!first.done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Async task timed out");
            }
            System.out.println(
                    "externalUsesWorker=" + (first.executedBy.get() != caller));

            Target second = new Target();
            WorkPort wrapper2 = new DispatchWrapper(second, executor);

            wrapper2.entry(); // wrapper -> target.entry -> this.work
            if (!second.done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Self-call timed out");
            }
            System.out.println(
                    "selfCallUsesCaller=" + (second.executedBy.get() == caller));
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy với Java 17 trở lên:

~~~bash
javac ProxyBoundaryDemo.java
java ProxyBoundaryDemo
~~~

Stdout của lần chạy thành công:

~~~text
externalUsesWorker=true
selfCallUsesCaller=true
~~~

Giải thích:

1. `wrapper1.work()` gọi `executor.execute(target::work)`; method `Target.work()` được chạy trên worker thread khác thread main. `CountDownLatch` chứng minh task đã chạy trước khi đọc kết quả.
2. `wrapper2.entry()` chỉ ủy quyền tới `target.entry()`. Trong `entry()`, lời gọi `work()` trực tiếp trên `Target`, không hề đi qua `DispatchWrapper.work()`; nó chạy trên caller.
3. Không dùng `Thread.sleep` để đoán lịch thread. Chúng ta so sánh **đối tượng Thread** và chờ latch, nên kết quả không phụ thuộc tên thread hoặc độ nhanh của máy.

AspectJ sau khi weave có thể đặt interception tại `execution` của `work()`, khác với mô hình wrapper. Do đó cần một **integration test riêng với Spring + weaver** để xác nhận behavior thực, không dùng ví dụ Java thuần này làm bằng chứng đã cấu hình AspectJ thành công.

## 10. Kiểm thử self-invocation thật với Spring

Một test đúng nên có hai tình huống tách biệt: **PROXY mode** và **ASPECTJ mode đã weave**. Không cố bật/tắt mode liên tục trong cùng một ApplicationContext đang chạy.

Tệp **AsyncProbeService.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncProbeService {

    public CompletableFuture<String> callInside(
            CountDownLatch entered, CountDownLatch release) {
        return asyncWork(entered, release); // self-invocation
    }

    @Async("exportExecutor")
    public CompletableFuture<String> asyncWork(
            CountDownLatch entered, CountDownLatch release) {
        entered.countDown();
        try {
            if (!release.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Wait timed out");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        }
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }
}
~~~

Đây là **Spring service test**, cần ApplicationContext, không có `main` riêng. Sử dụng hai latch truyền qua từng lần gọi để không lưu trạng thái mutable của một test trong singleton bean.

### Test PROXY mode

- Bean/test khác inject `AsyncProbeService`; gọi `asyncWork(entered, release)` từ ngoài qua proxy sẽ dispatch tới executor nếu configured đúng.
- Với `callInside(entered, release)`, body `asyncWork` được gọi trực tiếp trong cùng bean. Vì nó đang chờ `release` nên lời gọi `callInside` **bị chặn** cho đến khi test thả latch.
- Để tránh chính test thread tự bị chặn, hãy gọi `callInside` từ một test helper thread, chờ `entered` rồi thả `release`. Kiểm tra tên thread trả về là helper thread.
- Dùng timeout ở mọi lần chờ và dọn helper executor trong `finally`.

### Test ASPECTJ mode đã weave

- Tạo ApplicationContext khác với `@EnableAsync(mode=ASPECTJ)`; bảo đảm `AsyncProbeService` đã weave bằng CTW/LTW và `exportExecutor` có capacity.
- Gọi `callInside(entered, release)` từ test thread. Execution của `asyncWork` được weave nên có thể dispatch tới executor và trả `CompletableFuture` trước khi body thoát khỏi `release.await()`.
- Chờ `entered.await(timeout)` để biết worker đã vào body; trước khi thả `release`, future chưa nên hoàn thành.
- Thả `release`, lấy kết quả bằng `future.get(timeout)`, so sánh thread name với thread gọi; tốt hơn có thể truyền recorder/thread identity qua test fixture.
- Bật weave-info trong môi trường test hoặc kiểm tra class woven để chứng minh class/method thực sự được advice.

**Tránh nhầm kết quả:** một executor kiểu `SyncTaskExecutor` hoặc `CallerRunsPolicy` khi bão hòa có thể chạy body trực tiếp trên caller **dù advice AspectJ đã hoạt động**. Do đó test dùng executor bất đồng bộ thật, queue còn chỗ, và tách rõ “advice đã interception” khỏi “thread nào thực thi”.

## 11. Những điều AspectJ không tự giải quyết

### Kiểu trả về và exception

Method mang `@Async` phải theo chữ ký được hỗ trợ: `void` hoặc `Future` phù hợp, bao gồm `CompletableFuture`. Trong worker, target method có thể trả `CompletableFuture.completedFuture(value)`; caller giữ Future do advice quản lý. Một method trả `String` rồi annotate `@Async` không tự trở thành method bất đồng bộ hợp lệ chỉ nhờ weaving. `AnnotationAsyncExecutionAspect` còn xác định lỗi/cảnh báo weaving cho các chữ ký không phù hợp.

Với `@Async void`, exception trong body thường đi tới `AsyncUncaughtExceptionHandler`. Với `Future`/`CompletableFuture`, caller có đường quan sát exceptional completion. Nếu executor từ chối ngay khi submit, `TaskRejectedException` có thể xuất hiện tại ranh giới gửi. Không được nhầm submission rejection với body failure.

### Executor overload và shutdown

Cả PROXY và ASPECTJ đều cần executor thực tế. Khi queue đầy, `AbortPolicy` báo rejection; `CallerRunsPolicy` có thể chạy trên caller; một chính sách discard có thể làm mất task im lặng. AspectJ không tự tăng `maxPoolSize`, không tự retry và không hứa một lời gọi async luôn trả rất nhanh.

### Transaction và thread context

Async work trên thread khác không tự thừa hưởng transaction, security context, MDC hay `ThreadLocal` từ caller. Nếu gọi việc trước khi transaction commit, worker có thể thấy dữ liệu chưa sẵn sàng hoặc request sau đó rollback. Cần xác định ranh giới transaction và cơ chế after-commit/outbox khi yêu cầu.

Bật AspectJ cho `@Async` **không** tự chuyển `@Transactional` sang AspectJ mode; từng hệ thống advice có cấu hình riêng. Nếu ứng dụng dùng nhiều advice, cần test hành vi composition/thứ tự và thread context theo đúng kịch bản.

### Độ bền và nhiều replica

Một task đang chờ trong RAM queue của một JVM có thể mất khi tiến trình crash. AspectJ weaving không phải hàng đợi bền vững và không giúp các replica tự chuyển giao job. Với công việc phải hoàn thành sau restart, dùng job store/message queue, retry, idempotency và trạng thái đủ quan sát.

## 12. Chi phí vận hành và tương thích phiên bản

Khi chọn weaving, phải lập kế hoạch cho:

- **Version matrix:** AspectJ compiler/weaver phải đọc được bytecode của JDK đang dùng; Spring modules và `spring-aspects` phải tương thích. Nâng JDK có thể cần nâng AspectJ.
- **Build reproducibility:** ở CTW, artifact release phải đúng là class đã weave; không để bước đóng gói dùng nhầm bản biên dịch Java thuần.
- **Classloader:** ở LTW, agent/weaver phải có hiệu lực khi class cần can thiệp đang nạp; Boot executable JAR, WAR, app server và test runner có thể có cách classloading khác nhau.
- **Phạm vi weave:** hạn chế package cần thiết khi có thể, tránh chạm quá nhiều class; nhưng không loại nhầm class mục tiêu.
- **Instrumentation khác:** code coverage, profiler, tracing agent và bytecode enhancer khác có thể cùng tham gia biến đổi class; cần thử nghiệm phối hợp.
- **Startup/debug:** LTW có thể tăng thời gian nạp class, CTW tăng thời gian build; stack trace và bytecode sau weave có thể khó debug hơn.
- **Deployment/rollback:** cần giữ cùng JVM flags, dependencies và artifacts ở CI, staging, production; nên có kiểm thử smoke khi cập nhật runtime.

Không dựa vào việc thấy `spring-aspects` trong dependency tree để kết luận đã weave. Dùng kết hợp **weave-info + integration test + kiểm tra runtime artifact**.

## 13. Lỗi và ngộ nhận thường gặp

1. **Chỉ thêm `mode=ASPECTJ` rồi cho rằng xong.** Phải có aspect và weaving thật.
2. **Chỉ thêm `spring-aspects`.** Aspect definition trong classpath không tự sửa bytecode.
3. **Chỉ thêm `aspectjweaver` dependency nhưng không chạy agent/CTW.** Thư viện chưa tự được kích hoạt.
4. **Dùng `@EnableAspectJAutoProxy` như một công tắc weaving.** Đó là Spring proxy-based AOP trong trường hợp thông thường.
5. **Bật `proxyTargetClass=true` để sửa self-call.** JDK/CGLIB đều không tự thay đổi đường gọi `this.method()` trên target.
6. **Dùng `javac` thay `ajc` ở pipeline CTW.** Không tạo class đã weave.
7. **Đặt `-javaagent` sai vị trí trong lệnh JVM.** Startup option phải đứng trước `-jar` hoặc tên main class.
8. **Quên `spring-aspects` runtime hoặc aspect metadata.** Weaver không thấy Spring async aspect cần áp.
9. **Sai package/classloader hoặc include/exclude rule.** Class đích không bị weave.
10. **Class được nạp trước khi LTW hoạt động.** Không thể coi việc đổi cấu hình sau đó là retroactive weaving.
11. **Đặt annotation chỉ trên interface mà không kiểm chứng execution của implementation.** Với AspectJ nên annotate trực tiếp implementation method/class khi cần.
12. **Mong private/final/constructor/lifecycle callback tự được hỗ trợ vô điều kiện.** Weaving rộng hơn proxy nhưng pointcut và hợp đồng `@Async` vẫn giới hạn.
13. **Cho rằng AspectJ tự tạo worker pool.** Executor vẫn phải được cấu hình, sizing và theo dõi overload.
14. **Cho rằng @Transactional tự đổi mode cùng @Async.** Mỗi advice có đường cấu hình riêng.
15. **Kiểm thử bằng `Thread.sleep` hoặc `isDone()` trên task cực nhanh.** Dùng latch và thread identity.
16. **Dùng nhiều config `@EnableAsync` cạnh tranh trong cùng test.** Kiểm tra một mode rõ ràng trên từng context.
17. **Bỏ qua `CallerRunsPolicy` khi đo thread identity.** Advice thành công vẫn có thể chạy task trên caller.
18. **Đổi sang AspectJ chỉ để chữa một self-invocation đơn giản.** Tách bean thường dễ bảo trì hơn.
19. **Không thử cấu hình startup trên production packaging.** Agent/classloader khác có thể làm LTW không hoạt động.
20. **Đồng nhất `@Async` với durable job.** Weaving không bảo đảm xử lý sau crash/restart.

## 14. Quy trình quyết định thực tế

Hãy đi từ phương án ít phức tạp nhất:

1. **Chứng minh vấn đề.** Xác định có thực sự self-invocation, method không đi qua proxy, hay chỉ là executor policy khiến code chạy trên caller.
2. **Kiểm tra Spring-managed bean.** Method được gọi từ reference inject không? Có `@EnableAsync` trong context đúng không? Method có kiểu trả về đúng không?
3. **Đánh giá refactor.** Tách method async sang bean khác; hoặc dùng explicit `TaskExecutor` ngay tại nơi cần dispatch.
4. **Định nghĩa yêu cầu nâng cao.** Nếu cần interception nhiều self-call ở lớp không thể refactor hợp lý, mới cân nhắc AspectJ.
5. **Chọn CTW hoặc LTW.** CTW ưu tiên artifact được cố định khi build; LTW phải quản lý agent/classloader/runtime.
6. **Kiểm soát dependencies.** Dùng `spring-aspects` cùng phiên bản Spring tương thích, AspectJ weaver/compiler phù hợp bytecode level.
7. **Kiểm chứng weaving thật.** Dùng weave-info và integration test của cả external call lẫn self-call; không chỉ đọc annotation.
8. **Đo vận hành.** Startup, memory, thread pool, queue, p95/p99, lỗi submit/worker, tương tác với transaction và tracing.
9. **Có đường rollback.** Giữ cách cấu trúc bean đơn giản đủ để quay về proxy mode nếu việc vận hành weaving không phù hợp.

| Bối cảnh | Khuyến nghị |
| --- | --- |
| Các bean gọi nhau qua Spring injection | Giữ `AdviceMode.PROXY` |
| Chỉ một self-call không async | Tách bean/explicit executor trước |
| Có hàng loạt self-call cần interception, refactor không khả thi | Cân nhắc ASPECTJ + weaving + integration test |
| Không kiểm soát được JVM agent và build pipeline | Tránh phụ thuộc vào ASPECTJ mode |
| Vấn đề thật là queue đầy/latency cao | Thiết kế lại executor/backpressure, không đổi advice mode |
| Cần xử lý job bền vững qua restart | Job table/durable queue, không phải AspectJ |
| Có nhiều bytecode agents hoặc classloader đặc thù | Thử nghiệm triển khai trước khi quyết định |
| Muốn code dễ hiểu và dễ debug | Proxy mode với ranh giới bean rõ ràng thường thuận lợi |

## 15. Câu hỏi tự kiểm tra

1. `@EnableAsync` không ghi `mode` thì mặc định dùng gì?
2. Vì sao `this.perform()` trong cùng bean có thể không chạy async dù `perform` có `@Async`?
3. Bật `proxyTargetClass=true` có sửa self-invocation không? Tại sao?
4. Tại sao `@EnableAspectJAutoProxy` không đồng nghĩa với compile-time/load-time weaving?
5. Những điều kiện nào phải cùng đúng để `@EnableAsync(mode=ASPECTJ)` thực sự interception lời gọi nội bộ?
6. CTW khác LTW ở thời điểm nào và cần chú ý class nạp trước lúc weaver hoạt động ra sao?
7. `spring-aspects` và `aspectjweaver` chỉ nằm trong dependency tree có đủ để khẳng định self-call được weave không?
8. Vì sao `@Async` đặt trên implementation method rõ ràng hơn khi dùng AspectJ?
9. Dùng latch và thread identity để kiểm tra self-call với proxy/AspectJ như thế nào?
10. Tại sao AspectJ không tự thay đổi `@Transactional`, executor policy, hoặc bảo đảm xử lý qua restart?
11. Khi `CallerRunsPolicy` kích hoạt, một method đã weave có thể vẫn chạy trên caller không?
12. Nếu chỉ có một vấn đề self-invocation, lựa chọn nào thường ít rủi ro vận hành hơn AspectJ?

## 16. Tài liệu tham khảo

- [Spring Framework — @EnableAsync API: PROXY và ASPECTJ](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Using AspectJ with Spring Applications](https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html)
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html)
- [Spring source — AnnotationAsyncExecutionAspect.aj](https://github.com/spring-projects/spring-framework/blob/main/spring-aspects/src/main/java/org/springframework/scheduling/aspectj/AnnotationAsyncExecutionAspect.aj)
- [Spring source — spring-aspects META-INF/aop.xml](https://github.com/spring-projects/spring-framework/blob/main/spring-aspects/src/main/resources/META-INF/aop.xml)
- [AspectJ — Official Documentation](https://eclipse.dev/aspectj/doc/latest/index.html)

**Ghi nhớ:** `AdviceMode.PROXY` xử lý lời gọi qua Spring proxy nên self-invocation thường bỏ qua `@Async`. `AdviceMode.ASPECTJ` có thể can thiệp tại method execution kể cả self-call **nếu bytecode đã được weave**. Đây là giải pháp nâng cao đòi hỏi AspectJ tooling, Spring aspects, runtime/build configuration và integration test; nếu tách bean giải quyết được vấn đề, phương án proxy vẫn thường rõ ràng và nhẹ hơn.