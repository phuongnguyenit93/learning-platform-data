# Tự gọi method và bẫy self-invocation

## 1. Self-invocation là gì?

Self-invocation xảy ra khi một phương thức trong object gọi trực tiếp một phương thức khác của chính object đó, thường qua this hoặc gọi tên phương thức không có tiền tố. Trong Spring, kiểu gọi nội bộ này có thể bỏ qua các hành vi được áp dụng bằng proxy AOP, chẳng hạn @Async, @Transactional, @Cacheable hoặc các advice khác.

Vấn đề thường gặp với xử lý bất đồng bộ là một class có phương thức được đánh dấu @Async, nhưng phương thức khác trong cùng class gọi nó. Người viết mong Spring chuyển công việc sang executor, trong khi lời gọi thực tế đi thẳng tới object đích và chạy trên thread hiện tại.

Ví dụ:

~~~java
@Service
public class ReportService {
    public void generateReport() {
        sendEmailAsync(); // Self-invocation
    }

    @Async
    public void sendEmailAsync() {
        // Gửi email ở background thread theo kỳ vọng.
    }
}
~~~

Nếu một bean khác gọi reportService.generateReport() qua Spring proxy, phương thức generateReport được thực thi. Nhưng lời gọi sendEmailAsync() bên trong class là lời gọi trực tiếp trên target object. Proxy không nhận được lời gọi thứ hai, nên interceptor của @Async không được kích hoạt.

Kết quả là sendEmailAsync() chạy đồng bộ trên thread đang gọi generateReport(). Annotation vẫn nằm trên method, nhưng đường gọi đã không đi qua proxy.

## 2. Vì sao proxy không bắt được lời gọi nội bộ?

Trong chế độ proxy mặc định, Spring tạo một proxy bao quanh bean. Khi một bean khác gọi phương thức qua proxy, proxy có thể áp dụng interceptor trước khi chuyển lời gọi tới object đích.

Có thể hình dung:

1. Caller gọi generateReport() trên proxy.
2. Proxy chuyển lời gọi tới object ReportService thật.
3. Code trong generateReport gọi this.sendEmailAsync().
4. Lời gọi thứ hai diễn ra trực tiếp trên object thật.
5. Proxy không được đi qua lần nữa, vì vậy @Async không có cơ hội submit task vào executor.

Sơ đồ:

~~~text
Bean gọi từ bên ngoài
        |
        v
   Spring Proxy
        |
        v
 ReportService.generateReport()
        |
        | this.sendEmailAsync()
        v
 ReportService.sendEmailAsync()
        |
        v
 Chạy trên thread hiện tại
~~~

Để @Async hoạt động, lời gọi đến phương thức bất đồng bộ phải đi qua proxy Spring. Điều này giải thích vì sao gọi method từ một bean khác có thể chạy async, còn gọi cùng method bằng this lại chạy đồng bộ.

## 3. Phân biệt hai cách gọi

Giả sử sendEmailAsync() có @Async:

| Cách gọi | Có đi qua proxy ở lời gọi async? | Kết quả |
|---|---|---|
| Bean A gọi reportService.sendEmailAsync() | Có, nếu reportService là Spring proxy | Task được submit vào executor |
| ReportService.generateReport() gọi this.sendEmailAsync() | Không | Method chạy trên thread hiện tại |
| ReportService.generateReport() gọi một bean emailWorker.sendEmailAsync() | Có, nếu emailWorker là Spring proxy | Task được submit vào executor |
| Tạo object bằng new ReportService() rồi gọi method | Không có Spring proxy | @Async không được áp dụng |

Điểm cần kiểm tra là object nhận lời gọi có phải bean proxy do Spring quản lý hay không và lời gọi có thực sự đi qua proxy hay không. Chỉ nhìn annotation trên method chưa đủ để kết luận công việc sẽ chạy bất đồng bộ.

## 4. Cách sửa tốt nhất: tách method async sang bean riêng

Cách dễ hiểu và dễ kiểm thử nhất là đưa công việc bất đồng bộ sang một bean khác. Bean gọi sẽ giữ phần điều phối; worker chịu trách nhiệm thực hiện công việc nền.

Ví dụ:

~~~java
@Service
public class EmailWorker {
    @Async("taskExecutor")
    public CompletableFuture<Void> sendConfirmation(String orderId) {
        // Gửi email.
        return CompletableFuture.completedFuture(null);
    }
}
~~~

~~~java
@Service
public class OrderService {
    private final EmailWorker emailWorker;

    public OrderService(EmailWorker emailWorker) {
        this.emailWorker = emailWorker;
    }

    public void createOrder(String orderId) {
        // Lưu đơn hàng và hoàn tất phần nghiệp vụ đồng bộ.
        emailWorker.sendConfirmation(orderId);
    }
}
~~~

OrderService gọi phương thức trên bean EmailWorker được inject bởi Spring. Lời gọi đi qua proxy của EmailWorker, vì vậy @Async được kích hoạt.

Cách tách này có một số lợi ích:

- Ranh giới giữa phần điều phối và phần xử lý nền rõ ràng.
- Lời gọi async đi qua proxy một cách tự nhiên.
- Worker có thể được kiểm thử độc lập.
- Có thể gán executor riêng cho nhóm công việc.
- Không cần lấy proxy của chính bean hoặc phụ thuộc vào AopContext.

Nếu caller cần chờ kết quả, hãy giữ lại CompletableFuture và quyết định rõ thời điểm join hoặc xử lý callback. Nếu caller không cần kết quả, có thể bỏ qua Future, nhưng vẫn phải có cách quan sát lỗi của task nền.

## 5. Dùng self-injection khi chưa thể tách bean

Một cách khác là inject proxy của chính bean rồi gọi qua tham chiếu đó. Ví dụ có thể dùng @Lazy để trì hoãn việc phân giải tham chiếu:

~~~java
@Service
public class ReportService {
    @Autowired
    @Lazy
    private ReportService self;

    public void generateReport() {
        self.sendEmailAsync();
    }

    @Async("taskExecutor")
    public CompletableFuture<Void> sendEmailAsync() {
        // Gửi email.
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Trong ví dụ, self là tham chiếu tới proxy. Khi generateReport gọi self.sendEmailAsync(), lời gọi đi qua proxy và interceptor @Async có thể chạy.

Tuy nhiên, self-injection tạo phụ thuộc vòng giữa bean và proxy của chính nó. Nó có thể làm cấu hình khó hiểu, phức tạp hóa khởi tạo bean và khiến ranh giới trách nhiệm kém rõ. Chỉ dùng khi việc tách bean không phù hợp với thiết kế hiện tại.

Nếu chọn cách này, hãy kiểm tra context thực tế có tạo proxy đúng và bảo đảm tham chiếu được inject là proxy, không phải target object.

## 6. Dùng AopContext.currentProxy() trong trường hợp đặc biệt

Spring có thể cho phép lấy proxy hiện tại bằng AopContext.currentProxy(), nếu proxy được cấu hình để expose. Cách này đòi hỏi cấu hình exposeProxy=true và làm code phụ thuộc trực tiếp vào Spring AOP:

~~~java
@EnableAspectJAutoProxy(exposeProxy = true)
@Configuration
class AopConfiguration {
}
~~~

~~~java
public void generateReport() {
    ((ReportService) AopContext.currentProxy()).sendEmailAsync();
}
~~~

Cách này có thể giải quyết self-invocation vì lời gọi được chuyển qua proxy đang xử lý request hiện tại. Tuy nhiên, nó làm code khó đọc và khó kiểm thử hơn, đồng thời gắn chặt business class với AOP infrastructure.

Ưu tiên tách worker thành bean riêng. Chỉ cân nhắc AopContext khi có lý do kiến trúc rõ ràng và đội ngũ chấp nhận sự phụ thuộc này.

## 7. Điều kiện để @Async hoạt động

Ngay cả khi lời gọi đi qua proxy, @Async vẫn cần cấu hình đúng:

**Bật async processing.** Đặt @EnableAsync trên một class cấu hình được nạp vào ApplicationContext.

**Bean do Spring quản lý.** Object phải được tạo và quản lý bởi container. Object được tạo bằng new không có proxy async.

**Gọi qua proxy.** Caller phải sử dụng bean proxy, thường là dependency được inject từ Spring.

**Chọn executor.** Có thể dùng executor mặc định hoặc chỉ định bean cụ thể bằng @Async("taskExecutor"). Với công việc production, nên cấu hình thread pool có giới hạn và chính sách từ chối task phù hợp.

**Chọn kiểu trả về.** Phương thức có thể trả void, Future hoặc CompletableFuture. Nếu trả void, exception trong thread nền không được chuyển ngược về caller. Nếu cần kết quả hoặc muốn kết hợp nhiều công việc, dùng CompletableFuture.

Ví dụ cấu hình:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
    @Bean(name = "taskExecutor")
    public ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("async-");
        return executor;
    }
}
~~~

Cấu hình pool phải phù hợp với đặc điểm CPU/I/O, giới hạn database và dịch vụ bên ngoài. Không nên tăng thread hoặc queue vô hạn để che giấu tình trạng quá tải.

## 8. Self-invocation ảnh hưởng tới @Transactional và các annotation khác

Self-invocation không chỉ là bẫy của @Async. Các annotation dựa trên proxy AOP cũng có thể bị bỏ qua khi method được gọi trực tiếp trong cùng object.

Ví dụ:

~~~java
@Service
public class PaymentService {
    public void processPayment() {
        saveAuditRecord();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAuditRecord() {
        // Mong muốn có transaction độc lập.
    }
}
~~~

Nếu processPayment được gọi qua proxy nhưng saveAuditRecord được gọi bằng this, interceptor transaction của saveAuditRecord không chạy. Phương thức có thể tiếp tục trong transaction hiện tại hoặc không có transaction, tùy ngữ cảnh gọi.

Điều tương tự cần lưu ý với @Cacheable, @Retryable và các advice proxy-based khác. Hãy xác định annotation đang dựa vào cơ chế proxy hay cơ chế khác trước khi kết luận hành vi.

Với @Transactional, tách thao tác cần transaction riêng sang một bean khác thường là cách rõ ràng nhất:

~~~java
@Service
public class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAuditRecord() {
        // Ghi audit trong transaction mới.
    }
}
~~~

~~~java
@Service
public class PaymentService {
    private final AuditService auditService;

    public PaymentService(AuditService auditService) {
        this.auditService = auditService;
    }

    public void processPayment() {
        auditService.saveAuditRecord();
    }
}
~~~

Lời gọi qua AuditService proxy cho phép Spring áp dụng propagation REQUIRES_NEW theo cấu hình.

## 9. Kiểu proxy và giới hạn method

Spring AOP thường dùng JDK dynamic proxy khi bean có interface phù hợp, hoặc class-based proxy khi cần proxy class cụ thể. Cơ chế proxy ảnh hưởng đến những phương thức có thể được intercept.

- Với JDK dynamic proxy, caller truy cập các phương thức được khai báo trên interface proxy.
- Với class-based proxy, Spring tạo subclass của class đích; class và method không thể bị override, chẳng hạn class final hoặc method final, không thể được intercept theo cách subclass proxy.
- Private method không phải điểm gọi có thể được intercept qua proxy theo mô hình này.
- Self-invocation vẫn bỏ qua proxy dù Spring dùng loại proxy nào.

Khi thiết kế API async, nên dùng method public, bean Spring rõ ràng và dependency được inject qua constructor. Điều đó giúp người đọc nhận ra ranh giới gọi qua proxy và tránh các giới hạn do loại proxy.

## 10. Ví dụ hoàn chỉnh có thể chạy

Ví dụ dùng Java 17 và Spring Framework 6.2.0. Chương trình gọi cùng một công việc theo hai cách: self-invocation trong một bean và gọi qua một worker bean riêng.

Kết quả mong đợi:

- Self-invocation chạy trên thread main.
- Gọi qua AsyncWorker chạy trên thread có tiền tố async-.

Tạo file src/main/java/demo/SelfInvocationAsyncDemo.java:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.CompletableFuture;

public class SelfInvocationAsyncDemo {
    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {
            String callerThread = Thread.currentThread().getName();

            String selfThread = context
                .getBean(SelfInvokingService.class)
                .callInternally()
                .join();

            String workerThread = context
                .getBean(DelegatingService.class)
                .callThroughWorker()
                .join();

            System.out.println("Caller thread: " + callerThread);
            System.out.println("Self-invocation thread: " + selfThread);
            System.out.println("Separate-bean thread: " + workerThread);

            if (!callerThread.equals(selfThread)) {
                throw new AssertionError(
                    "Self-invocation unexpectedly used another thread"
                );
            }
            if (callerThread.equals(workerThread)) {
                throw new AssertionError(
                    "Separate bean did not execute asynchronously"
                );
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    static class AppConfig {
        @Bean(name = "taskExecutor")
        ThreadPoolTaskExecutor taskExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("async-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        SelfInvokingService selfInvokingService() {
            return new SelfInvokingService();
        }

        @Bean
        AsyncWorker asyncWorker() {
            return new AsyncWorker();
        }

        @Bean
        DelegatingService delegatingService(AsyncWorker worker) {
            return new DelegatingService(worker);
        }
    }

    public static class SelfInvokingService {
        public CompletableFuture<String> callInternally() {
            return asyncOperation();
        }

        @Async("taskExecutor")
        public CompletableFuture<String> asyncOperation() {
            return CompletableFuture.completedFuture(
                Thread.currentThread().getName()
            );
        }
    }

    public static class AsyncWorker {
        @Async("taskExecutor")
        public CompletableFuture<String> asyncOperation() {
            return CompletableFuture.completedFuture(
                Thread.currentThread().getName()
            );
        }
    }

    public static class DelegatingService {
        private final AsyncWorker worker;

        public DelegatingService(AsyncWorker worker) {
            this.worker = worker;
        }

        public CompletableFuture<String> callThroughWorker() {
            return worker.asyncOperation();
        }
    }
}
~~~

Tạo file pom.xml tại thư mục gốc:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>self-invocation-async-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <configuration>
                    <mainClass>demo.SelfInvocationAsyncDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chạy tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java
~~~

Stdout dự kiến:

~~~text
Caller thread: main
Self-invocation thread: main
Separate-bean thread: async-1
~~~

Giải thích:

1. AnnotationConfigApplicationContext nạp AppConfig và bật @EnableAsync.
2. Spring tạo proxy cho SelfInvokingService và AsyncWorker vì các bean có method @Async.
3. callInternally() được gọi qua bean proxy, nhưng bên trong method gọi asyncOperation() trực tiếp trên target object. Vì vậy, lời gọi không đi qua proxy và trả về tên thread main.
4. DelegatingService gọi asyncOperation() trên bean AsyncWorker được inject. Đây là lời gọi qua proxy, nên task chạy trên executor và trả về tên thread async-1.
5. join() đợi CompletableFuture hoàn tất để chương trình có thể in và so sánh tên thread.
6. Context được đóng bằng try-with-resources; executor được Spring quản lý theo lifecycle.

## 11. Kiểm thử self-invocation

Không nên chỉ kiểm tra method có annotation @Async. Hãy kiểm tra hành vi quan sát được qua proxy.

Một số cách kiểm thử hữu ích:

- Ghi lại tên thread hoặc dùng một giá trị nhận diện thread để so sánh caller và worker.
- Dùng CountDownLatch hoặc CompletableFuture để đồng bộ kiểm thử, tránh sleep tùy ý.
- Kiểm tra method gọi qua bean khác thực sự chạy trên executor đã cấu hình.
- Kiểm tra self-invocation chạy đồng bộ trong trường hợp cần chứng minh lỗi.
- Kiểm tra exception và timeout của task async.

Với bài kiểm thử integration, hãy khởi tạo ApplicationContext thật để Spring tạo proxy và executor. Unit test tạo class bằng new chỉ kiểm tra logic Java thông thường, không kiểm tra được việc @Async có được proxy áp dụng hay không.

Không nên khẳng định một thứ tự log cố định giữa các thread nếu chương trình không có cơ chế đồng bộ. Dùng Future, latch hoặc assertion dựa trên thread identity để kiểm tra kết quả ổn định.

## 12. Lỗi thường gặp và cách xử lý

- Gọi this.asyncMethod(): lời gọi nội bộ bỏ qua proxy; chuyển method sang bean khác và gọi qua dependency.
- Nghĩ rằng @Async tự tạo thread cho mọi lời gọi: annotation chỉ có tác dụng khi invocation đi qua async proxy.
- Tạo object bằng new: object không được Spring quản lý nên không có proxy.
- Đánh dấu method private hoặc final rồi kỳ vọng class proxy intercept: dùng method có thể được proxy intercept và kiểm tra loại proxy.
- Bật @Async nhưng quên @EnableAsync: cấu hình async annotation processing trong ApplicationContext.
- Gọi method qua một tham chiếu target thay vì bean proxy: lấy dependency từ Spring container hoặc constructor injection.
- Bỏ qua Future: nếu cần biết kết quả, giữ CompletableFuture và xử lý hoàn tất/lỗi.
- Dùng return void rồi mong exception truyền về caller: cấu hình AsyncUncaughtExceptionHandler hoặc xử lý lỗi trong listener/service nền.
- Dùng self-injection cho mọi trường hợp: ưu tiên tách bean để ranh giới proxy rõ ràng.
- Nhầm @Async với @Transactional: hai annotation có mục đích khác nhau, nhưng đều có thể bị ảnh hưởng bởi self-invocation khi chạy qua proxy.

## 13. Quy trình áp dụng

1. Xác định method cần chạy bất đồng bộ và caller thực tế của nó.
2. Kiểm tra caller có gọi qua Spring proxy hay gọi trực tiếp trong cùng class.
3. Nếu có self-invocation, tách phần async sang bean riêng và inject qua constructor.
4. Bật @EnableAsync và cấu hình executor có giới hạn.
5. Chọn void hoặc CompletableFuture theo nhu cầu nhận kết quả và xử lý lỗi.
6. Kiểm tra method và loại proxy có cho phép interceptor hoạt động.
7. Viết integration test xác nhận thread thực thi, kết quả và exception.
8. Áp dụng cùng cách kiểm tra cho các annotation proxy-based khác như @Transactional và @Cacheable.

Self-invocation là hệ quả của cách Spring AOP dùng proxy để áp dụng interceptor. Khi một method gọi method khác trong cùng object, lời gọi nội bộ đi thẳng tới target và bỏ qua proxy. Tách công việc bất đồng bộ sang một bean riêng thường tạo ra ranh giới rõ ràng nhất để @Async hoạt động đúng như mong đợi.