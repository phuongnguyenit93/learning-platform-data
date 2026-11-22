# Vì sao phương thức tự gọi trong cùng bean không kích hoạt @Async ở chế độ proxy?

## 1. Vấn đề thường gặp: có @Async nhưng công việc vẫn chạy đồng bộ

Trong Spring Framework, `@Async` được dùng để yêu cầu Spring thực thi một method trên executor, thay vì tiếp tục chạy phần thân method ngay trên thread gọi. Một trường hợp rất dễ gây nhầm lẫn:

```java
@Service
public class MailService {

    public void register(String id) {
        validate(id);
        this.sendMail(id); // Tự gọi trong cùng bean.
    }

    @Async("mailExecutor")
    public void sendMail(String id) {
        // Gửi email hoặc công việc tốn thời gian.
    }

    private void validate(String id) {
        // Kiểm tra dữ liệu.
    }
}
```

Đây là **fragment minh họa**, chưa phải chương trình chạy độc lập; cần Spring-managed bean, cấu hình executor và bật hỗ trợ async. Rất nhiều người thấy có đủ `@Async`, `@EnableAsync` và một thread pool nhưng `sendMail()` vẫn chạy trên thread đang thực hiện `register()`.

**Nguyên nhân không phải do Spring bỏ sót annotation.** Với chế độ AOP proxy mặc định, Spring chỉ áp dụng async interceptor khi lời gọi method **đi qua proxy**. Lời gọi `this.sendMail(id)` nằm trong cùng object/target và **không đi qua Spring proxy**, nên interceptor không được kích hoạt.

Kết quả:

- Thread gọi `register()` trực tiếp chạy `sendMail()`.
- Nếu gửi email chờ mạng, thread gọi có thể bị chặn.
- Nếu method ném exception, đường truyền lỗi có thể khác với lần gọi được proxy xử lý.
- Có thể có bean proxy và executor hoàn toàn đúng, nhưng riêng đường self-invocation vẫn không async.

**Quy tắc ngắn:** có `@Async` trên method **không có nghĩa** mọi lời gọi đến method đó đều bất đồng bộ. Cần kiểm tra *đường đi của lời gọi*.

## 2. @Async hoạt động như thế nào trong Spring proxy mode?

Khi bật xử lý annotation bằng `@EnableAsync` trong Java config hoặc `<task:annotation-driven>` trong XML, Spring đăng ký hạ tầng xử lý `@Async`. Ở chế độ mặc định `AdviceMode.PROXY`, Spring có thể đưa một proxy vào ApplicationContext tại vị trí người dùng lấy bean.

Khái niệm đơn giản:

```text
                         ApplicationContext
                                |
                   bean exposed to callers
                                |
                        Spring AOP proxy
                                |
         external call to @Async method intercepted?
                                |
                    Async interceptor / advice
                                |
                       submit to executor
                                |
                    worker thread invokes target
                                |
                         method body runs
```

Khi một bean khác nhận dependency từ Spring, dependency đó có thể là **proxy** thay cho target gốc. Proxy có khả năng nhận lời gọi, kiểm tra advice, rồi quyết định submit task vào executor.

Điểm quan trọng là proxy không “viết lại” mọi lời gọi Java xuất hiện bên trong class. Khi bạn đã đi vào code của target, biểu thức `this.someMethod()` là lời gọi method trên chính instance đang thực hiện phần thân, không phải một lời gọi mới qua bean reference lấy từ ApplicationContext.

### 2.1. Hai đường gọi trông giống nhau nhưng có kết quả khác

```text
ĐƯỜNG A — Gọi qua bean/proxy từ bên ngoài:

Controller / Facade
      |
      v
Spring proxy (MailWorker)
      |
      +-- @Async interceptor --> mailExecutor.submit(...)
                                   |
                                   v
                              worker thread
                                   |
                                   v
                              MailWorker.deliver()

ĐƯỜNG B — Tự gọi bên trong cùng target:

Controller / Facade
      |
      v
Spring proxy (MailWorker)
      |
      v
MailWorker.selfCall()  [target method body]
      |
      +-- this.deliver() ---------> MailWorker.deliver()
                                     (KHÔNG vào lại proxy)
                                     (KHÔNG có async interceptor)
```

Ngay cả ở đường B, điểm vào `selfCall()` có thể được gọi qua proxy. Nhưng vì `selfCall()` không phải async advice point trong ví dụ, nó chỉ ủy quyền đến target. Khi target tự gọi `deliver()`, không phát sinh một lượt interception mới.

### 2.2. Không phải tính năng riêng của CGLIB

Spring AOP có thể dùng JDK dynamic proxy hoặc class-based proxy. Cả hai đều dựa trên nguyên lý interception ở **biên lời gọi đi qua proxy**.

- Với JDK dynamic proxy, các lời gọi khả dụng thường đi qua interface mà proxy implement.
- Với class-based proxy, Spring dùng subclass proxy, nên client có thể lấy bean theo class trong những tình huống hỗ trợ.
- **Cả hai cách không giải quyết self-invocation chỉ bằng việc đổi loại proxy.** Đặt `@EnableAsync(proxyTargetClass = true)` không tự biến `this.sendMail()` thành một lời gọi qua proxy.

Một sự thật ít hiển nhiên: `AopUtils.isAopProxy(bean) == true` chỉ xác nhận reference bạn đang cầm là proxy; nó **không bảo đảm** mỗi lời gọi bên trong target đều đi qua advice.

## 3. Điều kiện cần để @Async thực sự được chặn

Trong Spring Framework thuần, muốn một lời gọi được chạy async theo proxy mode thì cần xem đồng thời các điều kiện:

1. **Bật xử lý annotation:** có `@EnableAsync` hoặc cấu hình XML `<task:annotation-driven>` được load vào context phù hợp.
2. **Bean được Spring quản lý:** client phải sử dụng bean mà Spring tạo và post-process; đối tượng tự `new MailWorker()` ngoài container không tự nhận AOP advice.
3. **Đường gọi đi qua proxy:** bean khác gọi một method được advice intercept, thay vì target tự gọi bằng `this.method()`.
4. **Method phù hợp cơ chế proxy:** không trông đợi interception trên method `private`, method `final` với class-based proxy, hoặc lời gọi không thuộc bề mặt interface tương ứng của JDK proxy.
5. **Executor phù hợp:** nếu chỉ định `@Async("mailExecutor")`, cần có bean executor tương ứng; executor thực tế phải được cấu hình theo yêu cầu vận hành.
6. **Method không bị gọi quá sớm trong lifecycle:** tự gọi từ constructor hoặc callback khởi tạo như `@PostConstruct` không phải cách đáng tin để tạo lời gọi `@Async` qua proxy.

Mất một điều kiện có thể khiến behavior khác mong đợi. Tuy nhiên **self-invocation là lỗi về đường đi của lời gọi**, không sửa được chỉ bằng cách tăng pool hoặc thêm `@EnableAsync` lần nữa.

## 4. Ví dụ Java 21 + Spring Framework 6.2.1 chạy được

Ví dụ kiểm chứng độc lập ba đường gọi:

- **Self-invocation:** method của bean gọi `this.deliver(...)`.
- **External invocation:** code lấy bean từ Spring và gọi `deliver(...)` qua reference proxy.
- **Cross-bean invocation:** một Spring bean khác được inject dependency và gọi `deliver(...)`.

Chương trình chủ động kiểm tra thread gọi và prefix của executor, thay vì dùng `Thread.sleep(...)` để đoán thời điểm kết thúc. Kết quả in ra dưới dạng boolean để không phụ thuộc tên thread do Maven hoặc hệ điều hành đặt.

### 4.1. Cấu trúc

```text
async-self-demo/
├── pom.xml
└── src/main/java/demo/SelfInvocationDemo.java
```

### 4.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>async-self-demo</artifactId>
  <version>1.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.1</version>
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
          <mainClass>demo.SelfInvocationDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

Không cần Spring Boot để quan sát nguyên lý. Dependency `spring-context` cho phép cấu hình context, `@EnableAsync`, `ThreadPoolTaskExecutor` và sử dụng hạ tầng AOP cần thiết trong bài.

### 4.3. Tệp src/main/java/demo/SelfInvocationDemo.java

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

public class SelfInvocationDemo {
    public static class MailWorker {
        @Async("mailExecutor")
        public CompletableFuture<String> deliver(String id) {
            return CompletableFuture.completedFuture(
                    Thread.currentThread().getName() + "|" + id);
        }

        public CompletableFuture<String> selfCall(String id) {
            return this.deliver(id);
        }
    }

    public static class MailFacade {
        private final MailWorker worker;

        public MailFacade(MailWorker worker) {
            this.worker = worker;
        }

        public CompletableFuture<String> crossBeanCall(String id) {
            return worker.deliver(id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {
        @Bean("mailExecutor")
        public ThreadPoolTaskExecutor mailExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(2);
            pool.setQueueCapacity(8);
            pool.setThreadNamePrefix("mail-");
            return pool;
        }

        @Bean
        public MailWorker mailWorker() {
            return new MailWorker();
        }

        @Bean
        public MailFacade mailFacade(MailWorker worker) {
            return new MailFacade(worker);
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            String caller = Thread.currentThread().getName();
            MailWorker worker = context.getBean(MailWorker.class);
            MailFacade facade = context.getBean(MailFacade.class);

            String self = worker.selfCall("S").get(5, TimeUnit.SECONDS);
            String external = worker.deliver("E").get(5, TimeUnit.SECONDS);
            String crossBean =
                    facade.crossBeanCall("C").get(5, TimeUnit.SECONDS);

            System.out.println("proxy=" + AopUtils.isAopProxy(worker));
            System.out.println("selfCallOnCaller=" +
                    self.equals(caller + "|S"));
            System.out.println("externalCallOnPool=" +
                    (external.startsWith("mail-") && external.endsWith("|E")));
            System.out.println("crossBeanCallOnPool=" +
                    (crossBean.startsWith("mail-") && crossBean.endsWith("|C")));

            if (!AopUtils.isAopProxy(worker)
                    || !self.equals(caller + "|S")
                    || !external.startsWith("mail-")
                    || !crossBean.startsWith("mail-")) {
                throw new AssertionError("Async proxy behavior not as expected");
            }
        }
    }
}
```

### 4.4. Chạy và kết quả kiểm chứng

Chạy trong thư mục chứa `pom.xml`, có Maven và JDK 21 trở lên:

```bash
mvn -q -DskipTests compile exec:java
```

Output đã được biên dịch và chạy thực tế với Spring Framework 6.2.1 (có thể xuất hiện log riêng từ Maven/JVM tùy môi trường):

```text
proxy=true
selfCallOnCaller=true
externalCallOnPool=true
crossBeanCallOnPool=true
```

Diễn giải từng dòng:

- `proxy=true`: reference `worker` lấy qua context là một Spring AOP proxy.
- `selfCallOnCaller=true`: gọi `worker.selfCall("S")` cuối cùng đi đến `this.deliver("S")` trong target; phần thân `deliver` chạy trên đúng thread đã gọi `selfCall`.
- `externalCallOnPool=true`: gọi trực tiếp `worker.deliver("E")` từ bên ngoài target đi qua proxy nên interceptor submit công việc vào executor có thread prefix `mail-`.
- `crossBeanCallOnPool=true`: `MailFacade` được inject bean `MailWorker` từ Spring; lời gọi `worker.deliver("C")` trong facade đi qua proxy và thực thi trên pool.

Đây là phép so sánh được thiết kế để phân biệt **call path**: cùng method `deliver`, cùng annotation và cùng cấu hình, nhưng có đường chạy đồng bộ và có đường chạy bất đồng bộ.

Không in một tên thread cố định như `main` hoặc `mail-1` vì tên caller khi chạy qua Maven có thể khác; phép kiểm tra so sánh bằng reference thread name tại runtime và prefix đã đặt mới là phần ổn định. Ngoài ra, `Future.get(timeout)` bảo đảm chương trình đợi hoàn tất đúng lúc thay vì phụ thuộc thứ tự scheduler.

## 5. Phân tích chi tiết luồng chạy của ví dụ

### 5.1. Khi gọi worker.selfCall("S")

Mã ở caller:

```java
String self = worker.selfCall("S").get(5, TimeUnit.SECONDS);
```

Đây là một **fragment trích từ chương trình hoàn chỉnh**. Reference `worker` là bean proxy, nhưng `selfCall` không gắn `@Async`. Khi code bên trong target chạy đến:

```java
return this.deliver(id);
```

nó gọi trực tiếp method của target và bỏ qua proxy/interceptor `@Async`. Vì thế `Thread.currentThread().getName()` trong `deliver` bằng thread ban đầu của caller. Việc method trả về một `CompletableFuture` đã hoàn thành **không chứng minh rằng nó đã thực thi bất đồng bộ**.

### 5.2. Khi gọi worker.deliver("E")

Mã ở caller:

```java
String external = worker.deliver("E").get(5, TimeUnit.SECONDS);
```

Lời gọi đi qua proxy. Async advice chọn bean `mailExecutor` từ tên trong `@Async("mailExecutor")` và submit task. Worker thực thi phần thân method, hoàn thành `CompletableFuture`, sau đó caller lấy kết quả qua `get()`.

Lưu ý `get()` là lời gọi **blocking ở caller**, dù task được chạy trên pool. Ví dụ chủ động dùng nó để quan sát kết quả; trong đường HTTP production nhạy latency, không nên submit rồi đợi vô hạn ngay lập tức nếu mục tiêu là giải phóng request thread.

### 5.3. Khi gọi facade.crossBeanCall("C")

`MailFacade` nhận `MailWorker` qua constructor injection:

```java
public MailFacade(MailWorker worker) {
    this.worker = worker;
}
```

Dependency này được container cung cấp, có thể là reference proxy. Do đó khi facade gọi `worker.deliver("C")`, nó chạm đúng advice. Đây là một hướng sửa lỗi self-invocation rõ ràng vì biến dependency thể hiện **ranh giới giữa orchestration và công việc nền**.

### 5.4. Vì sao không chỉ nhìn tên thread?

Nếu một method `@Async` bên ngoài đã được gọi qua proxy, nó sẽ bắt đầu chạy trên worker. Nếu *bên trong worker ấy* lại dùng `this.otherAsync()` để tự gọi method khác, method bên trong vẫn chạy ngay trên **cùng worker**, không tạo lượt submit mới.

Vì thế, chỉ thấy log trên `mail-1` không đủ để kết luận mọi annotation async lồng nhau đã được chặn. Cần phân biệt:

- **Ai đưa lời gọi đầu tiên lên pool?**
- **Method đang quan sát có thực sự đi qua proxy không?**
- **Có tạo một task/submission mới hay chỉ là lời gọi Java thường trong worker?**

## 6. Cách sửa ưu tiên: tách công việc async sang bean riêng

Khi một service vừa xử lý yêu cầu vừa muốn gửi công việc nền, phương án dễ bảo trì là **tách trách nhiệm**. Ví dụ thiết kế:

```java
@Service
public class NotificationWorker {
    @Async("mailExecutor")
    public CompletableFuture<Void> send(String id) {
        // Công việc nền: tải dữ liệu, gửi thông báo, ghi log phù hợp.
        return CompletableFuture.completedFuture(null);
    }
}

@Service
public class RegistrationService {
    private final NotificationWorker notificationWorker;

    public RegistrationService(NotificationWorker notificationWorker) {
        this.notificationWorker = notificationWorker;
    }

    public void register(String id) {
        // Xử lý đăng ký và kiểm tra hợp lệ.
        notificationWorker.send(id); // Lời gọi sang bean được inject.
    }
}
```

Đây là **fragment ứng dụng**, yêu cầu `@EnableAsync`, bean `mailExecutor`, các import `org.springframework.stereotype.Service`, `org.springframework.scheduling.annotation.Async` và `java.util.concurrent.CompletableFuture`, cùng logic nghiệp vụ thực tế.

Lợi ích:

1. `RegistrationService` chỉ quản lý luồng nghiệp vụ.
2. `NotificationWorker` quản lý ranh giới xử lý async.
3. Lời gọi từ `RegistrationService` đến `NotificationWorker` qua Spring-managed dependency có cơ hội đi qua proxy.
4. Dễ kiểm thử orchestration bằng mock/fake worker, kiểm thử async behavior bằng integration test riêng.
5. Tránh circular dependency hoặc gọi ngược ApplicationContext chỉ để lấy lại chính bean của mình.

**Chú ý:** nếu caller không giữ và quan sát `CompletableFuture`, phải có cơ chế ghi nhận thất bại phù hợp. Không nên bỏ Future của công việc quan trọng mà vẫn mặc định rằng nó sẽ hoàn tất.

Đây thường là giải pháp cân bằng nhất: cấu trúc rõ ràng và không cần can thiệp sâu vào Spring AOP.

## 7. Một lựa chọn khác: gửi tác vụ trực tiếp qua AsyncTaskExecutor

Không phải yêu cầu nào cũng cần annotation. Nếu một service có trách nhiệm điều phối task, có thể chủ động gọi `executor.submit(...)` hoặc `submitCompletable(...)`. Khi đó việc bất đồng bộ xảy ra **ngay tại lệnh submit**, không dựa vào việc Java gọi method qua proxy.

Ví dụ:

```java
@Service
public class ReportService {
    private final AsyncTaskExecutor executor;

    public ReportService(
            @Qualifier("reportExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    public CompletableFuture<String> startReport(String reportId) {
        return executor.submitCompletable(
                () -> generateReport(reportId));
    }

    private String generateReport(String reportId) {
        // Công việc nền có thể là private method vì
        // đây là Callable chạy do executor submit, không phải @Async proxy.
        return "report:" + reportId;
    }
}
```

Đây là **fragment**, cần Spring Framework có `AsyncTaskExecutor.submitCompletable(...)` (Spring 6.1+), một bean `reportExecutor` phù hợp, `@Service`, `@Qualifier` và imports tương ứng.

Ưu điểm:

- Không bị vấn đề self-invocation của `@Async` khi gọi private `generateReport`: worker nhận một lambda do `submitCompletable` tạo ra.
- Phân biệt rõ vị trí gửi task với business method.
- Có thể nhận `CompletableFuture<String>` để quản lý kết quả và exception.

Nhược điểm:

- Business/orchestration code biết đến executor API, thay vì chỉ dùng annotation.
- Cần quản lý kết quả, timeout, rejection và context propagation như mọi task nền.
- Không tự làm thao tác blocking I/O bên trong method thành nonblocking; nó chỉ chuyển nơi chạy sang executor.

**Lưu ý về API:** `TaskExecutor` cơ bản chỉ có `execute(Runnable)`; nếu cần `submitCompletable` thì dùng `AsyncTaskExecutor` phù hợp.

## 8. Có thể tự lấy proxy hoặc tự inject chính bean không?

Về kỹ thuật, một số giải pháp gián tiếp có thể đưa lời gọi đi qua proxy, chẳng hạn tra cứu bean qua `ApplicationContext`, self-injection thông qua một indirection phù hợp, hoặc dùng `AopContext.currentProxy()` khi AOP được cấu hình `exposeProxy` và lời gọi nằm trong đúng ngữ cảnh proxy.

Tuy nhiên đây **không phải phương án mặc định nên chọn**, vì:

- Class bắt đầu phụ thuộc trực tiếp vào container/AOP infrastructure.
- Self-injection có thể tạo vòng phụ thuộc, khó theo dõi trong constructor và phụ thuộc vào cấu hình Spring.
- `AopContext.currentProxy()` yêu cầu điều kiện bổ sung, không hoạt động với mọi lời gọi, và làm business code khó tái sử dụng ngoài proxy context.
- Người đọc code khó hiểu ranh giới nghiệp vụ hơn so với tách hai bean.

Nếu một thiết kế phải gọi chính proxy của mình để “kích hoạt annotation”, hãy xem đó là tín hiệu nên đánh giá lại trách nhiệm của class. **Tách worker sang bean riêng** thường đơn giản và kiểm thử tốt hơn.

## 9. AspectJ có xử lý self-invocation được không?

Có, nhưng phải hiểu đây là một **chế độ advice khác**, không chỉ là tùy chọn đổi kiểu proxy.

Với `@EnableAsync(mode = AdviceMode.PROXY)` (mặc định), Spring dùng AOP proxy: method self-call không đi qua advice.

Với `@EnableAsync(mode = AdviceMode.ASPECTJ)`, Spring có thể áp dụng advice bằng AspectJ weaving lên class. Khi **weaving thực sự được cấu hình và hoạt động** (compile-time hoặc load-time weaving, kèm dependencies tương ứng như `spring-aspects`), những lời gọi nội bộ có thể được intercept vì advice không còn phụ thuộc proxy boundary.

Đoạn khai báo minh họa:

```java
@Configuration
@EnableAsync(mode = AdviceMode.ASPECTJ)
public class AsyncAspectConfig {
    // Cần cấu hình và dependencies AspectJ weaving thực sự.
}
```

Đây **không phải ví dụ chạy độc lập**: thêm annotation này mà không có weaving được cấu hình đúng sẽ không tự khiến self-invocation bất đồng bộ. Hơn nữa, lựa chọn AspectJ làm tăng độ phức tạp build/deploy/debug. Hãy dùng khi có yêu cầu AOP liên quan nhiều call site thực sự đáng giá; không nên chuyển toàn bộ hệ thống sang weaving chỉ để sửa một method tự gọi.

**Không nhầm `proxyTargetClass=true` với AspectJ.** Tham số này chỉ chọn class-based proxies trong PROXY mode; self-call vẫn bypass advice.

## 10. Khi self-invocation làm thay đổi exception và Future semantics

Giả sử method `@Async` được thiết kế trả `CompletableFuture<String>`:

```java
@Async("mailExecutor")
public CompletableFuture<String> calculate() {
    // Có thể ném exception trước khi tạo Future hoặc
    // trả về CompletableFuture chứa kết quả.
    return CompletableFuture.completedFuture("ok");
}
```

Nếu caller đi qua proxy, Spring thực thi method trên executor và trả một async handle; exception của method được xử lý theo hợp đồng Future/CompletionStage tương ứng.

Nếu target tự gọi `this.calculate()`, async interceptor **không chạy**:

- Toàn bộ code trước câu lệnh `return` thực thi ngay trên thread đang gọi.
- Method trả về đúng object `CompletableFuture` do body tạo ra, không thông qua bước submit của async advice.
- Nếu body ném một runtime exception trực tiếp trước khi trả Future, exception đó có thể thoát **đồng bộ** trên lời gọi self-call.
- Với lời gọi qua proxy, các lỗi trong task thường được quan sát qua `Future.get()`/`CompletableFuture.join()`; nếu là `void` async method thì không có Future cho caller lấy lỗi, cần cấu hình `AsyncUncaughtExceptionHandler` hoặc cơ chế ghi nhận khác.

Vì vậy, self-invocation không chỉ ảnh hưởng hiệu năng. Nó có thể làm thay đổi cả **vị trí bắt lỗi, thời điểm phát sinh lỗi và behavior của request**.

### Phân biệt get() và join()

- `CompletableFuture.get()`: ném `ExecutionException` (cùng checked `InterruptedException`).
- `CompletableFuture.join()`: ném `CompletionException` (unchecked) khi có lỗi.
- Cả hai đều có thể **block caller** nếu Future chưa hoàn tất, nên không đặt tùy tiện trên event-loop hoặc request thread nhạy latency.

## 11. @Async lồng nhau: đã ở worker không có nghĩa lời gọi mới được async

Xem fragment:

```java
@Service
public class Pipeline {
    @Async("mailExecutor")
    public CompletableFuture<Void> outer() {
        this.inner();
        return CompletableFuture.completedFuture(null);
    }

    @Async("mailExecutor")
    public void inner() {
        // Bên trong outer() sẽ chạy trực tiếp trên thread hiện tại.
    }
}
```

Nếu một bean khác gọi `pipeline.outer()` qua proxy, `outer()` được chuyển sang pool. Nhưng `this.inner()` ở bên trong `outer()` vẫn không qua proxy nên `inner()` chạy trực tiếp trên chính thread đang xử lý `outer()`.

Điều này đặc biệt quan trọng khi bạn muốn tác vụ con được submit độc lập, chạy song song hay có cơ chế lỗi riêng. Chỉ thấy tên thread `mail-1` ở cả hai method không chứng minh đã có hai task khác nhau. Dùng instrumentation theo số task submit, log correlation id, timing có điều kiện và test controlled execution để xác định.

Tương tự, nếu `outer()` ném exception, cần kiểm tra Future của outer; không mặc định lỗi từ self-call bên trong được xử lý như một async submission độc lập.

## 12. Những tình huống khác thường bị nhầm với self-invocation

### 12.1. Thiếu @EnableAsync

Không có cấu hình annotation processing trong Spring Framework thuần thì `@Async` có thể chỉ còn là metadata trên method. Bật `@EnableAsync` hoặc XML `<task:annotation-driven>` phù hợp.

### 12.2. Bean không do Spring quản lý

`new MailWorker().deliver("E")` là lời gọi Java thông thường. Nó không đi qua proxy do container tạo.

### 12.3. Method private, final hoặc không thuộc interface proxy

Proxy-based AOP không thể chặn những lời gọi không khả dụng trên bề mặt proxy phù hợp. Private method và final method với class proxy không phải cách đặt `@Async` đáng tin. Với JDK proxy, hãy kiểm tra method được công khai qua interface đang được proxy.

### 12.4. Constructor và @PostConstruct

Trong constructor của target, bean chưa đi qua đầy đủ post-processing cần thiết. Tự gọi `@Async` từ constructor hoặc `@PostConstruct` không phải cách khởi tạo bất đồng bộ phù hợp. Theo hướng dẫn của Spring, có thể dùng **một Spring bean khởi tạo khác** gọi method `@Async` của target thông qua dependency đã sẵn sàng sau khi container tạo bean.

### 12.5. Executor thực thi đồng bộ

Mặc dù lỗi self-invocation khá phổ biến, vẫn có tình huống proxy hoạt động nhưng executor được cấu hình đồng bộ hoặc caller phải chờ kết quả ngay; hãy kiểm tra implementation thực tế và thời gian/blocking của caller, không kết luận chỉ dựa trên một log.

### 12.6. Mở rộng async pool không giải quyết root cause

Khi lời gọi bypass proxy, không có task nào được submit qua interceptor cho method ấy. Thay `corePoolSize`, `maxPoolSize`, `queueCapacity` hoặc prefix thread không thể biến self-call thành proxy call. Trước khi tuning, đo **task submission** và xác nhận đúng AOP boundary.

## 13. ThreadLocal, transaction và các tác động trên dữ liệu

Nếu lời gọi được chặn thành công và chạy ở worker, cần xem xét việc chuyển thread:

- **ThreadLocal/MDC:** giá trị gắn với thread HTTP/request không tự động có ở worker; cần cơ chế context propagation hoặc `TaskDecorator` phù hợp khi thật sự cần.
- **Security context:** không mặc nhiên được copy; dùng cơ chế propagation được thiết kế đúng thay vì lén giữ request object.
- **Transaction:** thread-bound transaction của caller không tự chuyển sang async worker. Một method `@Transactional` trên cùng bean cũng có self-invocation proxy limitation tương tự trong PROXY mode, nhưng phải phân biệt ngữ nghĩa transaction và async.
- **JPA persistence context:** entity/lazy-loaded dữ liệu có thể không còn hợp lệ khi worker chạy sau request/transaction; truyền identifier/DTO và mở transaction thích hợp ở phía worker.
- **Consistency:** công việc async có thể bắt đầu trước khi transaction của caller commit. Với hậu xử lý sau commit, cân nhắc event-after-commit hoặc outbox nếu yêu cầu độ tin cậy.

Một hệ quả đáng chú ý: trong self-call vô tình chạy đồng bộ, bạn có thể tưởng rằng `@Async` đang “mang được transaction/MDC”, trong khi thực ra chưa có thread switch nào xảy ra. Khi sửa sang cross-bean call, bất ngờ mất context là **hành vi đúng theo biên thread mới**. Cần thiết kế truyền context có chủ đích, không nên quay lại self-call để giữ state thread.

## 14. Kiểm thử chính xác và quan sát hiệu năng

### 14.1. Đừng chỉ kiểm tra isDone()

Một method gọi trực tiếp rồi trả `CompletableFuture.completedFuture(...)` sẽ có `isDone() == true`. Một async call chạy rất nhanh cũng có thể tạo Future đã hoàn tất trước khi bạn kiểm tra. Vì thế `isDone()` **không chứng minh** method có được interceptor chuyển sang thread khác hay không.

### 14.2. So sánh thread và dùng latch thay vì sleep

Ví dụ runnable trong mục 4 lấy thread name lúc caller bắt đầu, và bắt worker đặt tên qua `setThreadNamePrefix("mail-")`. Điều này giảm phụ thuộc timing so với `Thread.sleep(100)`.

Nếu test cần chứng minh caller **trả về trước khi worker hoàn thành**, hãy dùng `CountDownLatch`, `Phaser` hoặc test executor để giữ task ở một mốc xác định. Dùng timeout hữu hạn để tránh test bị treo khi logic thay đổi.

### 14.3. Quan sát proxy bằng AopUtils

`AopUtils.isAopProxy(bean)` trả true khi reference là AOP proxy. Nó hỗ trợ chẩn đoán: nếu false, một trong các điều kiện cấu hình có thể chưa thỏa. Nhưng kết quả true không khẳng định method cụ thể đã được advice chọn, vì advisor có pointcut và self-call vẫn bỏ qua proxy.

Cần xem cả proxy type, method signature, annotation, executor selection và call path. Một integration test đi qua bean reference như production sẽ có giá trị hơn unit test tự `new` target.

### 14.4. Không dùng thread name làm cơ chế nghiệp vụ

Prefix của executor phù hợp để debug và test minh họa. Trong production, đừng dùng `Thread.currentThread().getName().startsWith(...)` để quyết định tính đúng của transaction, quyền truy cập, thứ tự hoặc mức độ hoàn thành. Thread có thể được tái sử dụng, đổi cấu hình hoặc là virtual thread tùy implementation; hành vi nghiệp vụ cần dựa trên hợp đồng rõ ràng.

## 15. Bảng đối chiếu lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách sửa/kiểm tra |
| --- | --- | --- |
| `this.asyncMethod()` chạy ngay trong method cùng bean | Self-invocation bypass proxy | Tách bean hoặc submit qua executor |
| `@Async` đặt trên method nhưng mọi lời gọi đều đồng bộ | Chưa bật async processing hoặc không dùng Spring-managed bean | `@EnableAsync`, ApplicationContext, đúng method visibility |
| `AopUtils.isAopProxy(bean)` là true nhưng call vẫn đồng bộ | Đường gọi ở bên trong target hoặc method không được advice | Theo dõi call graph và method signature |
| Bật `proxyTargetClass=true` nhưng self-call vẫn đồng bộ | Class proxy vẫn cần external interception | Không xem CGLIB là cách sửa; tách bean |
| `@Async` method private/final không như mong đợi | Proxy không intercept được method | Tạo method public/khả dụng qua proxy |
| Gọi trong constructor hoặc `@PostConstruct` | Bean/proxy chưa sẵn sàng cho call đó | Khởi động thông qua bean khác sau lifecycle phù hợp |
| Đã chuyển sang bean khác nhưng có `this.otherAsync()` ở worker | Chỉ outer call qua proxy | Tách task con rõ ranh giới, không đánh đồng “đã trên pool” với interceptor mới |
| Sau khi sửa, thiếu MDC hoặc transaction | Worker chạy trên thread khác | Thiết kế context propagation và transaction riêng |
| Exception không còn ném ở caller | Async exception đi qua Future/handler | Thu nhận Future, cấu hình error reporting |
| Tăng thread pool mà không đổi kết quả | Không có async submission cho self-call | Xác nhận proxy boundary trước khi tuning |
| Test luôn pass vì Future đã completed | Test không kiểm tra thread hoặc concurrency | Dùng latch và kiểm tra đường gọi thực tế |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Có `@EnableAsync` và một bean `ThreadPoolTaskExecutor` đúng tên. Vì sao `this.sendMail(id)` vẫn chạy đồng bộ?

Vì trong `AdviceMode.PROXY`, lời gọi nội bộ trên target không đi qua proxy. Async interceptor không được áp dụng ở điểm gọi này, bất kể executor có tồn tại.

**Câu 2.** Đổi thành `@EnableAsync(proxyTargetClass = true)` có giải quyết được không?

Không. Tham số chỉ chọn class-based proxy thay vì JDK interface proxy trong PROXY mode; nó không tạo một interception cho self-call.

**Câu 3.** Một bean khác được inject `MailWorker`, gọi `worker.deliver()` thì có khác không?

Có. Khi reference được Spring cung cấp là proxy và method phù hợp advice, lời gọi từ bean khác đi qua proxy, nên `@Async` có thể submit task lên executor.

**Câu 4.** Nếu gọi `@Async outer()` từ bên ngoài, rồi bên trong `outer()` dùng `this.innerAsync()`, tại sao log của `innerAsync()` vẫn xuất hiện trên thread pool?

Vì `outer()` đã được chuyển sang worker; `innerAsync()` chạy **trực tiếp trên worker đó**, không phải vì có thêm một lượt async interception.

**Câu 5.** Muốn chạy async nhưng không muốn dùng Spring AOP proxy thì làm sao?

Tiêm `AsyncTaskExecutor`/`Executor` và gửi `Runnable` hoặc `Callable` bằng `execute/submit/submitCompletable`. Đây là explicit task submission và không phụ thuộc self-invocation proxy.

**Câu 6.** AspectJ có giúp chặn self-invocation không?

Có khi thực sự bật `AdviceMode.ASPECTJ` cùng AspectJ weaving và dependencies đầy đủ. Chỉ đổi annotation mà thiếu weaving chưa đủ. Với bài toán nghiệp vụ thông thường, tách sang bean khác thường ít phức tạp hơn.

## 17. Checklist trước khi đưa vào production

- **Điểm vào:** caller lấy reference từ Spring ApplicationContext hay dùng `new`?
- **Bật advice:** `@EnableAsync` hoặc XML `<task:annotation-driven>` đã được đăng ký ở context phù hợp?
- **Đường gọi:** method được gọi từ bean khác qua proxy hay chính `this.method()`?
- **Chữ ký:** method có thể được proxy intercept không? Có rơi vào private/final/interface mismatch?
- **Executor:** `@Async("...")` trỏ đúng bean, pool sizing/queue/rejection có giới hạn phù hợp?
- **Chứng minh:** có integration test chứng minh caller thread khác worker thread hoặc có submit độc lập, không dùng `Thread.sleep` đoán thời gian?
- **Kết quả/lỗi:** `void` hay `CompletableFuture`, ai quan sát exception, timeout và cancellation?
- **Ngữ cảnh:** transaction, security, logging MDC và dữ liệu JPA có được xử lý tại thread mới đúng cách?
- **Lifecycle:** đã tránh async call trong constructor/`@PostConstruct` và có chính sách shutdown rõ ràng?
- **Độ bền:** tác vụ quan trọng có cần outbox/broker thay vì chỉ queue trong tiến trình không?

## 18. Kết luận

**Lý do cốt lõi:** trong Spring `@Async` ở chế độ proxy mặc định, advice chỉ chạy khi một lời gọi đi qua Spring proxy. Lời gọi `this.asyncMethod()` trong cùng target bean là lời gọi Java thường, **không đi qua proxy**, nên không kích hoạt interceptor, không submit một task mới lên executor cho method đó.

Cách sửa dễ đọc, dễ test và thường nên ưu tiên: **đưa method async sang một Spring-managed bean riêng và gọi qua dependency được inject**. Nếu cần một vị trí gửi task tường minh, có thể dùng `AsyncTaskExecutor.submit(...)`/`submitCompletable(...)`. AspectJ weaving là phương án nâng cao cần cấu hình riêng, không đồng nghĩa với `proxyTargetClass=true`.

Đừng chẩn đoán chỉ từ annotation, tên thread hoặc `Future.isDone()`. Hãy xác minh **proxy boundary, đường gọi và task submission thực tế**.

### Tài liệu tham khảo

- [Spring Framework — Task Execution and Scheduling: Annotation Support](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework 6.2 — EnableAsync API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework 6.2 — Async API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework — Understanding AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)