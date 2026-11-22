# Đường đi lời gọi từ bên gọi qua proxy tới tác vụ bất đồng bộ

## 1. Vấn đề cốt lõi: ai thực sự chạy phương thức @Async?

Trong Spring Framework, đặt `@Async` lên một phương thức **không tự biến thân phương thức thành một thread mới**. Với chế độ mặc định, Spring dùng **AOP proxy** để chặn **lời gọi đi qua bean proxy**, chọn một executor, đóng gói thao tác gọi phương thức thành tác vụ và giao tác vụ cho executor thực hiện.

Vì vậy, để giải thích chính xác một lời gọi `service.generateReport()`, phải phân biệt ba đối tượng và hai đoạn thực thi:

1. **Caller**: controller, service hoặc một thành phần khác đang thực hiện lời gọi.
2. **Spring proxy**: đối tượng bean mà caller nhận qua dependency injection. Nó có cơ hội chặn lời gọi đủ điều kiện và áp dụng xử lý `@Async`.
3. **Target**: đối tượng chứa logic thật của phương thức. Với đường đi bất đồng bộ thông thường, logic target được gọi trong tác vụ do executor nhận.

Hai đoạn thực thi:

- **Trên caller thread**: đi vào proxy, xác định lời gọi bất đồng bộ, chọn executor, gửi tác vụ và trả quyền điều khiển/handle kết quả.
- **Trên worker thread** (với executor dựa trên thread pool): lấy tác vụ, gọi target method, thu kết quả hoặc ngoại lệ, rồi hoàn tất handle tương ứng.

`@Async` thay đổi **cách một lời gọi hợp lệ được định tuyến**, không phải định nghĩa cú pháp mới của Java. Khi lời gọi **không đi qua proxy**, annotation mặc định không được kích hoạt và method chạy trực tiếp như một lời gọi Java thông thường.

## 2. Sơ đồ đường đi caller → proxy → executor → worker → target

```text
Caller thread                            Executor / worker thread
-------------                            ------------------------
Controller / other bean
    |
    | 1. service.calculate(21)
    v
Spring-managed proxy
    |
    | 2. Async interceptor kiểm tra @Async
    | 3. Xác định executor (ví dụ "asyncPool")
    | 4. Đóng gói lời gọi target vào task
    | 5. submit(task) -----------------------------------+
    |                                                   |
    | 6. Trả Future/CompletableFuture                    v
    +----> caller tiếp tục                    Worker của asyncPool
                                                         |
                                                         | 7. invoke target
                                                         v
                                                   Target.calculate(21)
                                                         |
                                                         | 8. Tính ra kết quả
                                                         v
                                                 Hoàn tất Future
                                                         |
    | 9. caller gọi future.get() / callback <-----------+
    v
Nhận giá trị / lỗi / trạng thái cuối
```

Sơ đồ là **diễn giải về luồng xử lý điển hình**, không khẳng định mọi executor đều luôn tạo thread riêng: nếu cố tình cấu hình cơ chế thực thi đồng bộ hoặc thay executor bằng implementation có chính sách khác, đặc tính threading sẽ khác. Ngoài ra, thứ tự “caller tiếp tục” và “worker bắt đầu chạy” là **cạnh tranh theo lịch thread**; worker có thể hoàn thành rất nhanh ngay trước khi caller nhận handle.

Trọng tâm vẫn là: **đường đi qua proxy mới là điểm kích hoạt interceptor**, còn executor quyết định lịch chạy thực tế.

## 3. Điều kiện để lời gọi được proxy chặn

Một lời gọi `@Async` hoạt động theo cơ chế proxy khi thỏa đồng thời các điều kiện cần:

1. **Bật hỗ trợ async**: thường đặt `@EnableAsync` ở cấu hình Spring. Chỉ thêm `@Async` mà không kích hoạt xử lý async thì annotation có thể không tạo hành vi mong muốn.
2. **Target là bean được Spring quản lý**: Spring có cơ hội dùng bean post-processing để tạo/cấu hình proxy. Tự `new ReportService()` ngoài container sẽ không tự được bọc bởi proxy này.
3. **Caller gọi vào đối tượng proxy**: thường nhận qua constructor injection từ container, không tự gọi bằng `this` vào phương thức trong cùng target.
4. **Phương thức có thể được advice** theo kiểu proxy và cấu hình của ứng dụng: nên đặt `@Async` trên phương thức nghiệp vụ `public` được gọi từ một bean khác.
5. **Executor được chọn là hợp lệ và đang chấp nhận task**: nếu bean executor không tìm được, đã shutdown hoặc bị saturation, lời gọi có thể thất bại khi định tuyến/gửi việc.

Ví dụ lộ trình đúng:

```java
@Service
public class ApiService {
    private final ReportService reports;

    public ApiService(ReportService reports) {
        this.reports = reports; // Tham chiếu do Spring inject: có thể là proxy.
    }

    public void handleRequest() {
        reports.generateReport(); // Lời gọi từ bên ngoài qua proxy.
    }
}
```

Đoạn này là **mảnh mã trong ứng dụng Spring**, cần các bean và imports được khai báo. Nó chỉ mô tả điểm vào proxy; hãy xem các phần dưới để có dự án chạy độc lập và quan sát thread thực tế.

## 4. Proxy tạo và làm gì khi thấy @Async?

Spring có hạ tầng cho annotation `@Async`: khi bật `@EnableAsync`, framework đăng ký các thành phần nhận diện lời gọi đủ điều kiện và gắn async advice vào bean phù hợp. Ở chế độ proxy mặc định (`AdviceMode.PROXY`), advice được kích hoạt khi một caller gọi qua proxy.

Từng bước trên caller thread:

1. Caller đang giữ một tham chiếu tới bean. Tham chiếu ấy trông giống object Java thông thường nhưng thực tế có thể là proxy.
2. Lời gọi `service.method(args)` đi vào proxy.
3. Async interceptor tìm chính sách `@Async`, có thể lấy tên executor từ `@Async("beanName")`.
4. Interceptor đóng gói lời gọi target thành một tác vụ, thay vì lập tức gọi target ngay trên caller thread theo cách thông thường.
5. Tác vụ được đưa vào executor đã chọn (`Executor`/`AsyncTaskExecutor` thích hợp), nơi nó có thể bắt đầu chạy hoặc chờ queue.
6. Proxy trả về cho caller theo kiểu mà phương thức khai báo cho phép, không bắt caller tự tạo thread.

Từng bước trên worker thread:

1. Executor cấp một worker nhận task.
2. Task thực hiện chuỗi interceptor/target call cần thiết.
3. Logic phương thức `@Async` thật chạy trong môi trường của worker. Nếu nó trả `Future` hoặc `CompletableFuture`, Spring có thể bóc kết quả tương ứng để hoàn tất handle mà proxy trả cho caller.
4. Kết quả, ngoại lệ hoặc trạng thái hủy được phản ánh qua handle hoặc cơ chế báo lỗi của Spring.

**Không nên hình dung “proxy chính là thread worker”.** Proxy là cơ chế *chặn và định tuyến* lời gọi. Executor là cơ chế *thực thi task*. Target là nơi chứa *nghiệp vụ*.

## 5. Ví dụ Spring Framework có thể chạy với Java 17+

Ví dụ này dùng Spring Framework thuần (không yêu cầu Spring Boot) và `ThreadPoolTaskExecutor`. Nó chứng minh từ caller lấy bean qua context tới proxy, rồi phương thức target thực hiện trên thread có tiền tố được cấu hình.

Cấu trúc:

```text
async-call-path/
├── pom.xml
└── src/main/java/demo/AsyncProxyDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>async-call-path</artifactId>
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
                <version>3.14.0</version>
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

Nội dung `src/main/java/demo/AsyncProxyDemo.java`:

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncProxyDemo {

    @Bean("asyncPool")
    public ThreadPoolTaskExecutor asyncPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(10);
        pool.setThreadNamePrefix("async-worker-");
        return pool;
    }

    @Bean
    public WorkService workService() {
        return new WorkService();
    }

    public record Answer(int value, String workerThread) {}

    public static class WorkService {
        @Async("asyncPool")
        public CompletableFuture<Answer> calculate(int number) {
            Answer result = new Answer(
                    number * 2,
                    Thread.currentThread().getName()
            );
            return CompletableFuture.completedFuture(result);
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                 new AnnotationConfigApplicationContext(AsyncProxyDemo.class)) {
            WorkService service = context.getBean(WorkService.class);
            String callerThread = Thread.currentThread().getName();

            CompletableFuture<Answer> future = service.calculate(21);
            Answer answer = future.get(5, TimeUnit.SECONDS);

            System.out.println("value = " + answer.value());
            System.out.println("worker name matches = "
                    + answer.workerThread().startsWith("async-worker-"));
            System.out.println("different thread = "
                    + !callerThread.equals(answer.workerThread()));
        }
    }
}
```

Chạy ở thư mục dự án bằng Maven và JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.AsyncProxyDemo
```

Stdout do phần chương trình tạo ra:

```text
value = 42
worker name matches = true
different thread = true
```

Tại sao output này có ý nghĩa?

- `@EnableAsync` bật xử lý annotation trong context.
- `@Bean("asyncPool")` cung cấp executor có thread name `async-worker-`.
- `@Bean workService()` trả target `WorkService`, sau đó Spring có thể cung cấp proxy tới caller. Caller **lấy bean từ context**, không tự khởi tạo `new WorkService()` bên ngoài.
- `service.calculate(21)` đi qua async advice vì method `public` có `@Async("asyncPool")`.
- Worker tính `21*2` và ghi lại tên thread của chính nó.
- `future.get(5, TimeUnit.SECONDS)` đợi kết quả, nên dòng cuối không phụ thuộc vào việc worker nhanh hơn hay chậm hơn caller.
- Kết quả kiểm tra thread name và phép so sánh caller/worker đều đúng: logic target chạy trên worker của pool.

Ví dụ dùng một `record` Java 17 và phương thức `CompletableFuture.completedFuture` trong **target**. Điều này không có nghĩa caller đã nhận một kết quả hoàn tất đồng bộ: Spring interceptor trả về **handle bất đồng bộ** cho caller; `completedFuture` bên trong chỉ phù hợp chữ ký target và chuyển giao kết quả sau khi worker tính xong. Không được lấy thời điểm tạo handle làm bằng chứng target đã chạy xong.

Để người đọc dễ kiểm tra cú pháp, ví dụ có thể dùng trực tiếp với Spring `6.2.9` và JDK 17+. Hành vi đã được đối chiếu bằng JShell trên Spring `6.2.9`: giá trị 42 và hai kiểm tra thread đều `true`. Khi đóng context, Spring quản lý lifecycle của executor; service không tự gọi `shutdown()` cho bean dùng chung.

## 6. Vấn đề quan trọng: self-invocation bỏ qua proxy

Xem một bean có hai phương thức:

```java
@Service
public class InvoiceService {
    public void createInvoice() {
        this.sendEmailAsync(); // Gọi cùng object, bỏ qua proxy async.
    }

    @Async("asyncPool")
    public void sendEmailAsync() {
        // Logic gửi email.
    }
}
```

Đây là **mảnh mã minh họa** cần import `@Service`, `@Async` và cấu hình executor. Khi `createInvoice()` đã chạy **bên trong target**, `this.sendEmailAsync()` là một lời gọi trực tiếp trong cùng object; nó không đi qua proxy nên `@Async` **không được áp dụng cho lời gọi này** trong chế độ proxy mặc định.

Sơ đồ đối chiếu:

```text
ĐÚNG:   OtherBean --> InvoiceService proxy --> async advice --> executor --> target.sendEmailAsync()

BỎ QUA: OtherBean --> InvoiceService proxy --> target.createInvoice()
                                                |
                                                +--> this.sendEmailAsync()
                                                     (không quay lại proxy)
```

Cách thiết kế dễ hiểu nhất là **tách phương thức bất đồng bộ sang một bean khác**, rồi inject bean đó vào thành phần gọi:

```java
@Service
public class EmailTaskService {
    @Async("asyncPool")
    public void sendEmailAsync() {
        // Logic gửi email chạy theo executor.
    }
}

@Service
public class InvoiceService {
    private final EmailTaskService emailTasks;

    public InvoiceService(EmailTaskService emailTasks) {
        this.emailTasks = emailTasks;
    }

    public void createInvoice() {
        emailTasks.sendEmailAsync(); // Đi qua bean proxy của EmailTaskService.
    }
}
```

Hai class trên là **mảnh tích hợp**, cần nằm trong các tệp Java riêng tương ứng hoặc được khai báo phù hợp trong ứng dụng Spring; phương thức `createInvoice` không cần tự biết cách tạo thread.

Một số kỹ thuật như self-injection thông qua proxy hoặc lấy proxy từ context có thể thay đổi đường đi, nhưng làm code phụ thuộc vào AOP/container nhiều hơn. Tách trách nhiệm thành hai bean thường dễ hiểu và dễ kiểm thử.

## 7. Vì sao private/final hoặc tự new có thể làm @Async không chạy?

Trong chế độ `AdviceMode.PROXY`, proxy chỉ chặn những lời gọi **có thể đi qua nó**.

- **`private` method** không phải điểm vào phù hợp để gọi qua Spring proxy. Đừng đặt `@Async` lên một phương thức `private` rồi mong lời gọi nội bộ trở thành bất đồng bộ.
- **`final` class** không thể được subclass bởi class-based proxy. **`final` method** không thể bị class-based proxy override để chặn; cần thận trọng với thiết kế dựa trên CGLIB.
- **JDK dynamic proxy** chặn lời gọi qua **interface** được proxy triển khai; khi caller phụ thuộc interface, kiểu proxy và cách injection ảnh hưởng kiểu bean mà caller nhìn thấy.
- **Class-based proxy** (dựa trên subclass) có thể áp dụng khi không có interface phù hợp hoặc được cấu hình. Nó có giới hạn với `final` và một số phương thức không thể override.
- **Đối tượng được tạo bằng `new` ngoài Spring** không đi qua quy trình proxy của container.
- **Lời gọi qua `this`** vẫn bỏ qua proxy, dù phương thức có khai báo `public` và annotation hợp lệ.

Không nên khẳng định mọi `final` method luôn không thể được intercept trong **mọi loại proxy**: ràng buộc override áp dụng trực tiếp cho class-based proxy, còn JDK interface proxy là mô hình chặn khác. Tuy nhiên đối với code nghiệp vụ cần `@Async` đáng tin, nên dùng một phương thức public có thể advice và gọi qua bean Spring-managed.

Có thể kiểm tra trong thử nghiệm:

```java
import org.springframework.aop.support.AopUtils;

boolean proxied = AopUtils.isAopProxy(context.getBean(WorkService.class));
```

Đây là **mảnh kiểm tra** chạy trong phạm vi có `context` và `WorkService` của ví dụ. Nó chỉ xác nhận đối tượng đang cầm là AOP proxy, **không tự chứng minh mọi lời gọi ở mọi đường đi đều đi qua advice**.

## 8. @EnableAsync, tên executor và việc lựa chọn nơi thực thi

`@EnableAsync` kích hoạt xử lý annotation ở một Spring application context. `@Async` có thể chỉ định tên bean/qualifier của executor:

```java
@Async("asyncPool")
public CompletableFuture<Integer> calculate() {
    return CompletableFuture.completedFuture(42);
}
```

Đây là **mảnh method trong Spring-managed bean**, không phải một file Java độc lập.

`@Async("asyncPool")` gắn công việc với bean `asyncPool`. Nếu không chỉ định tên, Spring chọn executor theo cấu hình hỗ trợ async (`AsyncConfigurer`, bean executor phù hợp hoặc cơ chế fallback tùy framework/phiên bản). Vì vậy khi cần biết chính xác task chạy ở pool nào, hãy **khai báo và chọn executor rõ ràng** thay vì đoán theo tên thread mặc định.

Một số khác biệt quan trọng:

| Abstraction | Vai trò | Có tự tạo proxy @Async không? |
| --- | --- | --- |
| `@Async` | Đánh dấu phương thức là ứng viên chạy async | Không nếu không được hỗ trợ async và gọi đúng đường đi |
| `@EnableAsync` | Kích hoạt hạ tầng xử lý annotation | Bật cơ chế, còn mỗi lời gọi vẫn phải đi qua điểm chặn |
| `AsyncTaskExecutor` | Hợp đồng submit tác vụ bất đồng bộ | Không; nó là hợp đồng thực thi |
| `ThreadPoolTaskExecutor` | Implementation thread pool cho executor | Không; nó quản lý worker và queue |
| `AsyncAnnotationBeanPostProcessor`/advisor | Hỗ trợ áp async advice trên bean phù hợp | Tham gia tạo/gắn advice vào proxy |
| `Future`/`CompletableFuture` | Handle trạng thái và kết quả | Không; chúng không quyết định có proxy hay không |

`@EnableAsync` mặc định dùng `AdviceMode.PROXY`. Chế độ `AdviceMode.ASPECTJ` sử dụng weaving khi được cấu hình cùng các thành phần AspectJ cần thiết; nó có mô hình chặn khác và có thể xử lý self-invocation, nhưng **không phải** hành vi mặc định của Spring `@Async`. Đừng đổi mode chỉ để “sửa” self-invocation khi tách bean là thiết kế đơn giản hơn.

## 9. Điều gì xảy ra với void, Future và CompletableFuture?

Kiểu trả về của phương thức quyết định caller quan sát được gì sau khi proxy gửi tác vụ.

### void

```java
@Async("asyncPool")
public void writeAuditLog() {
    // Xử lý trên executor khi lời gọi đi qua proxy.
}
```

Đây là **mảnh method**. Caller không nhận `Future`, nên không thể gọi `get()` để nhận kết quả hoặc ngoại lệ. Nếu worker ném exception chưa được xử lý, Spring có cơ chế `AsyncUncaughtExceptionHandler` dành cho phương thức `void`; cần cấu hình logging/giám sát phù hợp. Exception nghiệp vụ ở worker không tự xuất hiện trong `try/catch` của caller sau một lời gọi `void` đã submit thành công.

### Future<T>

Phương thức `@Async` có thể khai báo `Future<T>`; phía proxy trả một Future dùng để nhận kết quả. Caller có thể `get()`, chờ timeout, hoặc quan sát hủy nếu implementation hỗ trợ.

### CompletableFuture<T>

`CompletableFuture<T>` hỗ trợ `thenApply`, `thenCompose`, `exceptionally`, `handle`, `whenComplete` và các phương thức kết hợp khác. Target có thể trả `CompletableFuture.completedFuture(value)` sau khi tính toán trên worker, trong khi caller nhận handle bất đồng bộ từ proxy. Callback không có hậu tố `Async` có thể chạy trên thread đang hoàn tất stage, vì vậy **không nên mặc định callback chạy trên caller thread**.

So sánh ngắn:

| Kiểu khai báo | Caller nhận | Nơi thấy lỗi của worker |
| --- | --- | --- |
| `void` | Không có handle hoàn tất | Handler/log/giám sát ở async infrastructure |
| `Future<T>` | `Future<T>` | `get()` ném `ExecutionException` chứa cause |
| `CompletableFuture<T>` | `CompletableFuture<T>` | `get()`, `join()`, `handle`, `exceptionally`... |

`get()` làm **thread gọi nó chờ** nếu task chưa hoàn tất. Như vậy `@Async` không có nghĩa mọi đoạn code sử dụng nó đều không chặn: nếu controller gọi `future.get()` ngay lập tức, HTTP request vẫn có thể phải đợi.

## 10. Hai loại lỗi khác nhau trong đường đi lời gọi

**Lỗi lúc submit** xảy ra trên nhánh caller → proxy → executor, ví dụ executor không tìm được, đã đóng hoặc hàng đợi/thread pool từ chối tác vụ. Spring `ThreadPoolTaskExecutor` thường báo `TaskRejectedException` khi quá tải. Đây là lỗi **chưa thực thi tác vụ hợp lệ**, có thể xuất hiện ngay khi gọi phương thức `@Async` (tùy cấu hình và thời điểm).

**Lỗi khi chạy task** xảy ra sau khi worker đã bắt đầu gọi target. Ví dụ truy vấn database lỗi hoặc logic ném `IllegalStateException`:

- Nếu return type là `Future<T>`, đọc lỗi qua `Future.get()` và `ExecutionException.getCause()`.
- Nếu là `CompletableFuture<T>`, có thể xử lý bằng `exceptionally`/`handle`, hoặc đọc `CompletionException` từ `join()`.
- Với `void`, không có handle trả cho caller; dùng handler/log/metric thích hợp.

Đừng đặt `try/catch` ở caller rồi cho rằng nó sẽ bắt mọi exception bên trong một `@Async void` chạy trên worker:

```java
try {
    bean.sendEmailAsync();
} catch (RuntimeException ex) {
    // Có thể bắt lỗi ở nhánh submit, không phải mọi lỗi chạy sau đó.
}
```

Đây là **mảnh minh họa** có bean được Spring inject. Nếu cần caller biết task thành công hay thất bại, hãy thiết kế API trả `CompletableFuture` hoặc một cơ chế lưu trạng thái tác vụ.

## 11. Ngữ cảnh theo thread không đi theo proxy một cách thần kỳ

Đường đi từ caller tới worker là một **ranh giới thread**. Điều này ảnh hưởng:

- **`ThreadLocal` và MDC logging**: giá trị gắn với caller thread không tự đảm bảo có mặt trên worker. Với executor có thread pool, worker được tái sử dụng; nếu truyền context, cần khôi phục và xóa sau mỗi task.
- **Security context**: cần cơ chế chuyển ngữ cảnh bảo mật có chủ ý, chẳng hạn executor wrapper của Spring Security khi dùng Spring Security.
- **Transaction context**: giao dịch Spring thông thường gắn với thread thực thi; không tự xem transaction của caller là một transaction chung cho worker. Nếu task cần transactional boundary, thiết kế giao dịch bên worker và kiểm tra advisor/transaction propagation phù hợp.
- **Trace context**: cần instrument hoặc context propagation tương thích với thư viện quan sát; tránh tưởng chỉ thêm `@Async` là trace ID tự xuất hiện trên worker.

Một `TaskDecorator` có thể wrap một `Runnable` thực thi để truyền và khôi phục một số context có chọn lọc. Nhưng decorator không thay thế cơ chế quản lý transaction và có chi phí; hãy làm rõ context nào thực sự cần cho nghiệp vụ.

Đừng chuyển nguyên object chứa dữ liệu mutable giữa caller và worker mà không bảo đảm an toàn đồng thời. Các hành động trước khi submit có một số bảo đảm *happens-before* theo contract của executor JDK, nhưng điều đó không làm `HashMap` dùng chung trở thành thread-safe nếu nhiều thread tiếp tục sửa đồng thời.

## 12. Proxy và worker ảnh hưởng gì đến thời gian trả về?

Có thể phân biệt các mốc thời gian:

```text
T0 caller invoke proxy
T1 executor nhận task
T2 proxy trả handle về caller
T3 worker bắt đầu chạy target
T4 target kết thúc
T5 Future hoàn tất
T6 caller xử lý callback/get
```

Đây là **mốc logic**, không phải thứ tự tuyệt đối giữa T2 và T3: worker có thể chạy trước khi proxy trả về caller. Với executor có queue, khoảng từ T1 tới T3 có thể dài đáng kể; như vậy thời gian từ caller nhận handle đến khi tác vụ hoàn tất chịu ảnh hưởng của cả **queue wait** và **execution time**.

Nếu đo hiệu năng, phân biệt:

1. **Submit latency**: caller mất bao lâu để đi qua proxy và được executor nhận việc.
2. **Queue wait**: bao lâu từ lúc submit tới lúc worker bắt đầu target.
3. **Execution time**: target thật chạy trong bao lâu.
4. **End-to-end completion**: toàn bộ thời gian từ yêu cầu tới kết quả cuối cùng.

`ThreadPoolTaskExecutor` có các tham số `corePoolSize`, `maxPoolSize`, `queueCapacity`; nếu queue còn chỗ, tăng `maxPoolSize` chưa chắc tăng số worker đang chạy. Sự khác biệt giữa “proxy đã trả về” và “task đã thực sự xong” là lý do phải đo **task completion**, không chỉ đo HTTP response khi request trả trạng thái accepted.

## 13. Cách chẩn đoán @Async không chạy trên thread khác

Khi một phương thức có `@Async` vẫn in cùng tên thread với caller, kiểm tra theo thứ tự sau:

1. **`@EnableAsync` đã có trong đúng application context chưa?** Một context khác hoặc thiếu cấu hình có thể khiến bean không được xử lý như kỳ vọng.
2. **Đối tượng caller gọi có phải bean do Spring inject không?** Nếu `new` trực tiếp, không có async proxy.
3. **Có self-invocation không?** `this.asyncMethod()` trong cùng target thường bypass proxy.
4. **Phương thức có được advice không?** Kiểm tra visibility, `final` đối với subclass proxy, lớp/class proxy và interface injection.
5. **Executor nào được chọn?** `@Async("name")` trỏ tới bean nào; cấu hình pool có thực sự khác caller thread không?
6. **Đã đo bên trong target chưa?** Chỉ xem thread trên caller sau khi gọi `@Async` không chứng minh worker chạy ở đâu.
7. **Có gọi `future.get()` ngay sau submit?** Điều này làm caller chờ, nhưng không có nghĩa target chạy trực tiếp trên caller.
8. **Có lỗi submit/rejection không?** Task chưa được nhận không thể chạy trên worker; nên quan sát queue, active workers và exception.

Mẹo đo tối giản (đoạn tích hợp Spring):

```java
String before = Thread.currentThread().getName();
CompletableFuture<Answer> future = service.calculate(21);
Answer answer = future.get(5, TimeUnit.SECONDS);

System.out.println("caller: " + before);
System.out.println("worker: " + answer.workerThread());
```

Hai tên thread đầy đủ **phụ thuộc runtime**, nên không dùng chúng làm stdout cố định trong tài liệu kiểm thử; ví dụ hoàn chỉnh ở mục 5 kiểm tra prefix thay vì yêu cầu một tên thread chính xác. Bên cạnh log, có thể kiểm tra `AopUtils.isAopProxy(bean)` để xác nhận loại tham chiếu nhưng vẫn cần thử **đường đi lời gọi thực sự**.

## 14. Một số ngộ nhận cần tránh

1. **“Có annotation `@Async` là chắc chắn chạy khác thread.”** Sai: phải bật hạ tầng, lời gọi đúng đường qua proxy, và executor phù hợp.
2. **“Spring proxy chỉ để logging.”** Sai: nó thực thi advice, có thể thay đổi cách lời gọi được xử lý, bao gồm submit task vào executor.
3. **“TaskExecutor tự nhận ra annotation.”** Không: hạ tầng `@Async` và proxy mới gắn hành vi async cho method; executor chỉ thực thi task đã được giao.
4. **“Gọi method `@Async` từ method cùng bean vẫn async.”** Trong proxy mode mặc định, self-invocation bypass advice.
5. **“Annotation chạy trên worker, còn mọi code trong target chạy trên caller.”** Ngược lại trong đường đi tiêu chuẩn: interceptor định tuyến, target chạy khi worker thực thi task.
6. **“Chỉ vì Future đã được trả về nên công việc đã xong.”** Future có thể còn pending/queue/running.
7. **“`@Async` tự chuyển transaction, MDC và security context từ caller.”** Không được mặc định; phải cấu hình truyền context và transactional boundary theo nhu cầu.
8. **“Method ném exception nên `try/catch` caller sẽ bắt được.”** Với lỗi worker async, cần Future, callback hoặc handler phù hợp.
9. **“Cứ tăng `maxPoolSize` thì worker sẽ lập tức tăng.”** Không đúng nếu queue còn rộng hoặc tác vụ đang chờ phụ thuộc bên ngoài.
10. **“`@Async` luôn tương đương `CompletableFuture.supplyAsync()`.”** Chúng đều hỗ trợ bất đồng bộ nhưng `@Async` phụ thuộc vào Spring proxy, bean lifecycle và interceptor; `supplyAsync` là API Java có lựa chọn executor riêng.
11. **“Một `@Async` method trên class cấu hình là cách chuẩn để khởi chạy job khi tạo bean.”** Không nên áp `@Async` trên phương thức `@Configuration` hoặc mong `@PostConstruct` trong cùng bean được proxy intercept. Hãy dùng thành phần điều phối sau khi bean sẵn sàng.

## 15. Tự kiểm tra

**Câu 1.** Controller inject `ReportService` từ Spring rồi gọi `calculate()` được đánh dấu `@Async`. Lời gọi đi qua những thành phần nào?  
**Đáp án:** Caller → bean proxy → async interceptor → executor/queue → worker → target method; kết quả/lỗi được phản ánh qua handle thích hợp nếu return type cho phép.

**Câu 2.** Trong cùng class, `run()` gọi `this.sendAsync()`. Tại sao không chạy async?  
**Đáp án:** Đây là lời gọi nội bộ trên target, không đi qua Spring proxy trong `AdviceMode.PROXY` mặc định.

**Câu 3.** `@Async("asyncPool")` có làm method chạy trên thread tên `asyncPool` không?  
**Đáp án:** Nó chọn executor bean/qualifier tên `asyncPool`; thread name và chính sách tạo thread do implementation/configuration quyết định.

**Câu 4.** Vì sao target `CompletableFuture.completedFuture(value)` không phủ định bản chất async?  
**Đáp án:** `completedFuture` được tạo **bên trong worker** để đáp ứng chữ ký target; proxy đã chuyển lời gọi sang executor và trả handle bất đồng bộ cho caller.

**Câu 5.** Worker ném exception trong `@Async void`. Có nên mong `try/catch` ngay sau lời gọi ở caller bắt được?  
**Đáp án:** Không; phải dùng handler/log/metric cho phương thức void hoặc thiết kế API trả Future/CompletableFuture để quan sát lỗi.

**Câu 6.** Có cách nào để self-invocation được intercept mà không tách bean?  
**Đáp án:** Có thể thay đổi thiết kế gọi qua proxy hoặc dùng `AdviceMode.ASPECTJ` với weaving phù hợp, nhưng tách tác vụ bất đồng bộ sang bean riêng là lựa chọn thường dễ hiểu và dễ bảo trì hơn.

**Ghi nhớ:** lời gọi bất đồng bộ trong Spring là kết quả của **đường đi qua proxy cộng với chính sách executor**. Khi phân tích bug hay performance, luôn tách *caller*, *proxy/interceptor*, *executor/queue*, *worker* và *target*.

### Tài liệu tham khảo

- [Spring Framework Reference — Task Execution and Scheduling (@Async, proxy mode, executor qualification)](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — @Async JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework — @EnableAsync JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework — AsyncAnnotationBeanPostProcessor JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/AsyncAnnotationBeanPostProcessor.html)
- [Spring Framework — ThreadPoolTaskExecutor JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
