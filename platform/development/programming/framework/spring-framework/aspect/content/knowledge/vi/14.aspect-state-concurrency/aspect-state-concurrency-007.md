# Chuyển luồng, `@Async` và giới hạn ngữ cảnh gắn với luồng trong Spring AOP

## 1. Vì sao Spring Aspect phải quan tâm đến chuyển luồng?

Spring AOP thường chặn **lời gọi phương thức đi qua Spring proxy**. `@Async` cũng dùng cơ chế proxy trong chế độ mặc định: khi caller gọi một phương thức đủ điều kiện, bộ chặn bất đồng bộ gửi công việc vào `TaskExecutor`, còn caller nhận lại ngay một `Future` / `CompletableFuture` hoặc kết thúc lần gọi `void`. Phần thân phương thức được thực thi sau đó trong worker.

```text
CALLER THREAD                              EXECUTOR / WORKER THREAD
    |                                                |
    |  otherBean.work()                               |
    v                                                |
 Spring AOP proxy                                     |
    |                                                |
 Async advisor --------- submit(task) --------------->|
    |                                                | AOP @Around (target)
    | future returned                                |   -> @Before / target
    |                                                |   -> @AfterReturning
    |                                                | completes future
    +---------------- await/result <-----------------+
```

Trong cấu hình Spring phổ biến, `AsyncAnnotationBeanPostProcessor` đặt advisor bất đồng bộ **trước các advisor hiện có** để chuyển luồng càng sớm càng tốt. Do đó một `@Around` áp dụng **trên chính phương thức `@Async`** thường chạy ở worker; một `@Around` trên **phương thức caller** chạy ở caller. Nếu ứng dụng dùng nhiều proxy, thay đổi thứ tự advisor hoặc `@EnableAsync(mode = AdviceMode.ASPECTJ)`, cần quan sát đường đi thực tế. `@Order` giữa các `@Aspect` không thay thế việc xác định vị trí async advisor.

**Phân biệt:** (a) thời điểm proxy gửi tác vụ; (b) thời điểm thân phương thức chạy; (c) thời điểm `Future` hoàn tất. Ba thời điểm này có thể thuộc các luồng khác nhau.

## 2. Điều kiện kích hoạt `@Async` và advice

1. Bật `@EnableAsync`, cung cấp executor thích hợp, có thể chọn rõ `@Async("workerExecutor")`. `@EnableAspectJAutoProxy` cần cho aspect `@Aspect` của ứng dụng; chỉ khai báo aspect không tự bật xử lý `@Async`.
2. Bean phải được Spring quản lý và lời gọi phải **đi qua proxy**. `this.work()` trong cùng bean là self-invocation, bỏ qua async advisor và các advice proxy của lời gọi ấy. Tách phương thức async sang bean khác là cách đơn giản để bảo đảm có ranh giới proxy.
3. Tránh áp dụng proxy advice cho `private` hoặc `final` method; proxy CGLIB không ghi đè được phương thức `final`, còn JDK proxy chỉ phơi bày API qua interface. `@Async` không được hỗ trợ trực tiếp trên callback vòng đời như `@PostConstruct`.
4. Với `@Async`, return phù hợp gồm `void`, `Future<T>`, `CompletableFuture<T>`. Phương thức trả giá trị bất đồng bộ có thể trả `CompletableFuture.completedFuture(value)` trong worker; proxy cung cấp future để caller theo dõi thực thi.
5. Không nhầm `@Async` với một aspect tự khai báo: Spring dùng `AsyncAnnotationAdvisor` / interceptor để thực thi hành vi bất đồng bộ. Trong các phương thức AOP, `ProceedingJoinPoint.proceed()` thực thi bước kế tiếp trong chuỗi chặn hiện hành.

### Vị trí advice quyết định ý nghĩa của phép đo

| Điểm chặn | Luồng thường chạy | Điều thực sự đo |
| --- | --- | --- |
| `@Around` của service **gọi** phương thức `@Async` | Caller | Thời gian gửi task / xử lý của caller |
| `@Around` của phương thức **đích** `@Async` | Worker (async advisor ngoài cùng) | Thời gian chạy phương thức đích |
| `@AfterReturning` trên caller nhận `CompletableFuture` | Caller | Đã **nhận future**, chưa chắc task hoàn tất |
| `future.whenComplete(...)` | Luồng hoàn tất future hoặc luồng gắn callback nếu future đã xong | Kết quả cuối cùng của stage được theo dõi |

Nếu cần đo end-to-end, lấy mốc trước khi gửi và kết thúc tại `whenComplete`; đừng kết luận “xong nghiệp vụ” chỉ vì `@AfterReturning` đã chạy.

## 3. Ví dụ Spring AOP chạy được trên Java 17+

Ví dụ này cố ý lưu mã yêu cầu vào `ThreadLocal` ở caller. Nó chứng minh aspect chạy tại worker nhưng **mã yêu cầu không tự đi theo**. Dùng Maven và Spring Framework 6.2.x; không cần Spring Boot.

Cấu trúc:

```text
async-aop-demo/
├── pom.xml
└── src/main/java/example/AsyncAspectDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>async-aop-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.8</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-aop</artifactId>
      <version>6.2.8</version>
    </dependency>
    <dependency>
      <groupId>org.aspectj</groupId>
      <artifactId>aspectjweaver</artifactId>
      <version>1.9.22</version>
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

`src/main/java/example/AsyncAspectDemo.java`:

```java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncAspectDemo {
    static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    static class Config {
        @Bean
        ThreadPoolTaskExecutor workerExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(5);
            executor.setThreadNamePrefix("worker-");
            return executor;
        }

        @Bean WorkService workService() {
            return new WorkService();
        }

        @Bean TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    static class WorkService {
        @Async("workerExecutor")
        public CompletableFuture<String> work() {
            System.out.println("target: " + Thread.currentThread().getName()
                    + ", request=" + REQUEST_ID.get());
            return CompletableFuture.completedFuture("seen:" + REQUEST_ID.get());
        }
    }

    @Aspect
    static class TraceAspect {
        @Around("execution(* example..*.work(..))")
        public Object around(ProceedingJoinPoint pjp) throws Throwable {
            System.out.println("advice before: "
                    + Thread.currentThread().getName()
                    + ", request=" + REQUEST_ID.get());
            Object result = pjp.proceed();
            System.out.println("advice after: "
                    + Thread.currentThread().getName()
                    + ", request=" + REQUEST_ID.get());
            return result;
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            REQUEST_ID.set("REQ-42");
            try {
                System.out.println("caller request=" + REQUEST_ID.get());
                CompletableFuture<String> future =
                        context.getBean(WorkService.class).work();
                System.out.println("result=" + future.get(5, TimeUnit.SECONDS));
            } finally {
                REQUEST_ID.remove();
            }
        }
    }
}
```

Chạy tại thư mục `async-aop-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.AsyncAspectDemo
```

`stdout` với executor một worker tên `worker-1`, advice ở worker và chưa có cơ chế truyền `ThreadLocal`:

```text
caller request=REQ-42
advice before: worker-1, request=null
target: worker-1, request=null
advice after: worker-1, request=null
result=seen:null
```

`future.get(5, TimeUnit.SECONDS)` đợi đến khi task hoàn tất nên thứ tự hiển thị ở ví dụ được xác định; không cần `sleep`. `ThreadLocal` có ngăn giá trị riêng trên từng luồng, worker không tự nhận `REQ-42`. Điều này **không phải** lỗi của pointcut `@Around`. Nếu dùng cấu hình proxy/executor khác, có thể có thêm log hoặc tên worker khác: hãy quan sát tên luồng thực tế.

## 4. Phân loại ngữ cảnh tại ranh giới executor

| Ngữ cảnh | Cơ chế phổ biến | Trên worker mới hoặc luồng pool |
| --- | --- | --- |
| `ThreadLocal` tùy chỉnh, mã tương quan, SLF4J MDC | Giá trị gắn với luồng | Không tự có; cần chuyển giao và dọn |
| `RequestContextHolder` (Spring MVC) | `RequestAttributes` theo luồng | Không mặc định có; request có thể kết thúc trước task |
| `LocaleContextHolder` | `Locale` theo luồng | Không mặc định có; có thể truyền `Locale` đã chụp |
| `SecurityContextHolder` của Spring Security | `SecurityContext` theo luồng (mặc định) | Không tự có; cần cơ chế truyền bảo mật riêng |
| Giao dịch `@Transactional` imperative | `TransactionSynchronizationManager` theo luồng | **Transaction caller không đi theo worker** |
| Micrometer observation / trace | Context snapshot và các accessor | Chỉ truyền khi được cấu hình hỗ trợ |
| `Reactor Context` trong WebFlux | Context của luồng dữ liệu reactive | Không đồng nhất với `ThreadLocal`; cần cầu nối nếu trộn mô hình |

Ngữ cảnh chưa hẳn nên sao chép toàn bộ. Với task chạy nền lâu hơn HTTP request, tham số như mã tương quan, `Locale` hoặc định danh nghiệp vụ đã kiểm tra thường bền vững và minh bạch hơn giữ nguyên `RequestAttributes`. Tránh chuyển tham chiếu request/session, tài nguyên giao dịch hoặc thông tin xác thực rộng không cần thiết.

### Trường hợp `@Transactional` và `@Async`

Với `PlatformTransactionManager`, Spring ràng buộc transaction imperative vào **luồng hiện tại**. Khi caller đang trong `@Transactional` gọi một bean khác có `@Async`, worker **không tham gia cùng transaction**; rollback phía caller không đồng nghĩa rollback phía worker. Nếu worker cần giao dịch, cho một phương thức chạy trong worker đi qua Spring transactional proxy để mở transaction **riêng**. Không sao chép các ThreadLocal nội bộ của `TransactionSynchronizationManager` sang worker bằng decorator.

### Trường hợp `RequestContextHolder` và `InheritableThreadLocal`

`RequestContextHolder` có cơ chế kế thừa tùy chọn, nhưng `InheritableThreadLocal` chỉ sao chép giá trị khi **tạo luồng con**, không chuyển giao đáng tin cậy cho thread pool **dùng lại** luồng. Nó còn dễ lộ ngữ cảnh cũ sang task khác. Trích riêng dữ liệu bất biến còn cần trước khi rời request; không bật chế độ kế thừa để “chữa” lỗi mất context trong pool.

## 5. Ba phương án xử lý đúng phạm vi Spring Aspect

### Phương án A: Truyền tham số rõ ràng

```java
@Async("workerExecutor")
public CompletableFuture<String> work(String requestId) {
    return CompletableFuture.completedFuture("seen:" + requestId);
}

// Caller trên một bean khác: service.work("REQ-42");
```

Đây là đoạn thay thế minh họa trong Spring bean ở trên, **không** phải chương trình độc lập. Tham số là dữ liệu bất biến, không phụ thuộc scheduler hay ThreadLocal. Phù hợp khi code nghiệp vụ có thể sửa chữ ký.

### Phương án B: `TaskDecorator` chụp/khôi phục context cho AOP

Nếu advice của bạn hoặc thư viện logging **phải đọc ThreadLocal**, gắn decorator lên **chính executor mà `@Async` dùng**. Trong `Config` của ví dụ, thay bean `workerExecutor()` bằng:

```java
@Bean
ThreadPoolTaskExecutor workerExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(1);
    executor.setMaxPoolSize(1);
    executor.setQueueCapacity(5);
    executor.setThreadNamePrefix("worker-");

    executor.setTaskDecorator(task -> {
        // Chụp ở lúc executor nhận tác vụ.
        String captured = REQUEST_ID.get();
        return () -> {
            // Worker có thể đang dùng lại: nhớ trạng thái cũ.
            String previous = REQUEST_ID.get();
            try {
                if (captured == null) REQUEST_ID.remove();
                else REQUEST_ID.set(captured);
                task.run();
            } finally {
                if (previous == null) REQUEST_ID.remove();
                else REQUEST_ID.set(previous);
            }
        };
    });
    return executor;
}
```

Khi chạy lại, advice và target nhìn thấy `request=REQ-42`, future cho `result=seen:REQ-42`. Quy tắc bắt buộc: **capture khi gửi task → restore ở worker → phục hồi trạng thái worker trong `finally`**. Không truyền trạng thái của task A sang task B khi pool dùng lại luồng. Với MDC, chụp `MDC.getCopyOfContextMap()`, áp dụng bằng `MDC.setContextMap(...)` hoặc `MDC.clear()`, và phục hồi MDC cũ trong `finally`. Nếu dùng nhiều decorator, phối hợp có chủ đích (ví dụ `CompositeTaskDecorator`), tránh ghi đè lẫn nhau.

### Phương án C: Dùng hỗ trợ tích hợp đúng loại context

- **Micrometer / Spring Framework 6.1+:** `org.springframework.core.task.support.ContextPropagatingTaskDecorator` có thể chuyển observation/MDC/context đã được đăng ký `ThreadLocalAccessor`. Ví dụ trên executor có đủ dependency: `executor.setTaskDecorator(new ContextPropagatingTaskDecorator());`. Nó **không tự hiểu mọi `ThreadLocal` tùy ý**. Spring Boot có tùy chọn tích hợp context propagation theo phiên bản; khi tự dựng executor phải xác minh decorator thực sự được cài.
- **Spring Security:** `org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor` bọc `AsyncTaskExecutor` và khôi phục `SecurityContext` trong thời gian thực thi task. Ví dụ minh họa: `new DelegatingSecurityContextAsyncTaskExecutor(rawExecutor)`. Đặt wrapper làm executor thực tế của `@Async` (ví dụ bean `securedExecutor` và `@Async("securedExecutor")`); tạo wrapper nhưng vẫn dispatch qua `rawExecutor` thì không có tác dụng.

Hai cơ chế trên phục vụ phạm vi context được hỗ trợ, **không truyền transaction của caller** và cũng không đảm bảo mọi ngữ cảnh tùy biến được sao chép. Hãy kiểm thử số lượng task nhiều và chi phí capture/restore.

## 6. Ngoại lệ, callback, luồng nối tiếp

**Khi có `CompletableFuture`:** lỗi worker xuất hiện ở future; `get()` ném `ExecutionException` bao nguyên nhân và `join()` thường ném `CompletionException`. Khi `@Async` trả `void`, caller thường không thể dùng `try/catch` quanh lần gọi để bắt lỗi worker; dùng `AsyncUncaughtExceptionHandler` để xử lý/log. Lỗi submit do executor từ chối có thể xuất hiện ngay khi gọi proxy, cần xử lý riêng.

**Khi thêm stage:** `thenApply` có thể chạy ở luồng hoàn thành future hoặc luồng gắn callback nếu future đã xong; `thenApplyAsync` sử dụng executor riêng hoặc executor mặc định. Vì thế decorator của lần gọi `@Async` **không cam kết** mọi stage sau đều được truyền context. Truyền giá trị qua tham số, hoặc chỉ định executor được trang bị decorator tại từng ranh giới thật sự cần.

**Khi dùng virtual threads:** việc sử dụng luồng ảo không làm `ThreadLocal` của caller tự động xuất hiện trong task được dispatch. Vẫn cần hiểu proxy và đường truyền ngữ cảnh. Đừng áp dụng phương án `InheritableThreadLocal` như một quy tắc chung cho mọi kiểu executor.

## 7. Những lỗi cần nhận diện

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra / khắc phục |
| --- | --- | --- |
| `@Async` chạy trên caller | `this.work()`, thiếu `@EnableAsync`, bean tạo bằng `new` | Gọi qua bean proxy, log thread name |
| Aspect thấy `ThreadLocal=null` | Ngữ cảnh ở caller chưa được truyền | Dùng tham số hoặc `TaskDecorator` |
| `@AfterReturning` chạy trước khi kết quả hoàn tất | Chỉ quan sát thời điểm trả future | Đo bằng `whenComplete` |
| Task B mang trace/user của task A | Quên phục hồi context khi pool dùng lại | Luôn `finally`, kiểm thử 2 task liên tiếp |
| Request/locale vắng hoặc không hợp lệ | Context gắn vòng đời request/luồng | Trích dữ liệu cần trước khi submit |
| Transaction worker không rollback cùng caller | Transaction imperative gắn luồng | Thiết kế transaction độc lập và xử lý đồng bộ nghiệp vụ |
| Worker ném lỗi nhưng caller không thấy | `@Async void` không có future | `CompletableFuture` hoặc `AsyncUncaughtExceptionHandler` |
| `@Order` không giải thích được vị trí luồng | Async advisor/proxy khác thứ tự bạn tưởng | Kiểm tra advisor thật, log caller/advice/target |

Bài kiểm thử tốt: executor **một worker**, đặt `REQUEST_ID` ở caller rồi submit task A, xóa ở caller và submit task B; khi có decorator, task A nhận mã A, task B không được nhận mã A. Thêm tình huống task A ném ngoại lệ để kiểm tra `finally` không rò rỉ. Dùng `CompletableFuture` hoặc `CountDownLatch` đồng bộ thay cho đoán thời gian bằng `sleep`.

## 8. Ghi nhớ

`@Async` tạo một **ranh giới thực thi** khi đi qua Spring proxy; vị trí advice quyết định nó chạy trên caller hay worker. ThreadLocal, MDC, request context, security context và transaction có cơ chế sống khác nhau; không mặc định chuyển sang thread pool. Ưu tiên tham số bất biến; khi cần truyền ngữ cảnh cho Spring Aspect hoặc thư viện, dùng executor/decorator chuyên biệt, phục hồi trạng thái trong `finally` và kiểm thử khi luồng được dùng lại. Đo thời điểm hoàn tất future thay vì nhầm với thời điểm phương thức đã trả future.

### Tài liệu Spring để đối chiếu

- `@Async`, executor và xử lý lỗi: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring AOP proxy và self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Thứ tự advice: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Transaction imperative gắn với luồng: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Async advisor trước existing advisors: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/scheduling/annotation/AsyncAnnotationBeanPostProcessor.html
- `ContextPropagatingTaskDecorator`: https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
- Spring Security context và concurrency: https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html
