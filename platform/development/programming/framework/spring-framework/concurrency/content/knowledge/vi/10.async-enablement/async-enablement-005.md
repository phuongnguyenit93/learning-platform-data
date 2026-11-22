# Giới hạn dùng @Async trên phương thức trong lớp @Configuration

## 1. Mục tiêu và vấn đề cần phân biệt

Trong Spring Framework, `@Configuration` có nhiệm vụ **khai báo và cấu hình bean**, còn `@Async` dùng để **gọi phương thức của một bean theo cách bất đồng bộ** thông qua cơ chế xử lý của Spring. Hai annotation này có thể xuất hiện trong cùng một ứng dụng, nhưng có một giới hạn dễ gây nhầm:

> **Spring không hỗ trợ `@Async` trên phương thức được khai báo bên trong một lớp `@Configuration`.**

Đây là nội dung được ghi trực tiếp trong Javadoc của `org.springframework.scheduling.annotation.Async` (bao gồm tài liệu Spring 5.3 và 6.x). Đừng suy luận rằng một phương thức trong lớp cấu hình sẽ chuyển sang worker thread chỉ vì đã gắn `@Async` và bật `@EnableAsync`.

Sau bài này, bạn có thể:

- Phân biệt **`@EnableAsync` đặt trên lớp `@Configuration` (đúng, được hỗ trợ)** với **`@Async` đặt trên phương thức bên trong chính lớp đó (không được hỗ trợ)**.
- Hiểu trách nhiệm của `@Configuration`/`@Bean` khi tạo bean và trách nhiệm của `@Async` khi xử lý lời gọi nghiệp vụ.
- Chuyển công việc bất đồng bộ sang bean `@Service`/`@Component` riêng, được Spring quản lý và gọi **qua proxy**.
- Tạo ví dụ Spring Framework 6.1.3, Java 17+ thực sự chạy được và xác minh thread thực thi.
- Phân biệt giới hạn này với các lỗi khác: tự gọi phương thức trong cùng instance, gọi quá sớm ở lifecycle, chưa bật async processing hoặc chọn nhầm executor.
- Kiểm tra xử lý lỗi, kiểu trả về `Future`/`CompletableFuture`, và lập kế hoạch refactor mà không phá vỡ khởi tạo bean.

**Phạm vi:** Spring Framework, Java-based configuration và `@Async` trong chế độ proxy thông dụng. Ví dụ dùng Java 17+ và Spring Framework 6.1.3, nhưng quy tắc **không hỗ trợ `@Async` trên method khai báo trong `@Configuration`** đã có trong Javadoc Spring 5.3 và vẫn có trong Spring 6.x. Nếu ứng dụng sử dụng AspectJ weaving, vẫn nên tổ chức theo các bean nghiệp vụ riêng và kiểm tra tài liệu phiên bản; đừng xem weaving là cách bỏ qua giới hạn được ghi rõ của annotation.

## 2. Quy tắc cốt lõi: nơi bật và nơi thực thi

### 2.1. Cách đúng: `@EnableAsync` trên lớp cấu hình

~~~java
@Configuration
@EnableAsync
public class AsyncConfig {
    // Các @Bean cấu hình executor hoặc dependency khác.
}
~~~

Đây là **fragment minh họa**, chưa phải một Java file hoàn chỉnh (cần import hai annotation). `@EnableAsync` kích hoạt cơ chế xử lý lời gọi bất đồng bộ trong **Spring application context**. Đặt nó trên lớp `@Configuration` là cách dùng được tài liệu Spring khuyến nghị.

`@EnableAsync` **không tự chạy mọi phương thức của lớp cấu hình trên worker thread**. Nó đăng ký thành phần xử lý annotation, để các phương thức `@Async` **hợp lệ trên bean khác** được Spring áp dụng interceptor/proxy theo cấu hình.

### 2.2. Cách sai: `@Async` nằm trên method khai báo trong `@Configuration`

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class WrongConfig {
    @Async
    public CompletableFuture<String> generateReport() {
        return CompletableFuture.completedFuture("report");
    }
}
~~~

Đoạn trên là **phản ví dụ về cách tổ chức**, dù cú pháp Java trông có vẻ hợp lệ. Theo hợp đồng annotation Spring, `@Async` **không được hỗ trợ trên phương thức khai báo trong lớp `@Configuration`**. Không được dựa vào đó để bảo đảm `generateReport()` chạy bất đồng bộ, không lấy một lần chạy ngẫu nhiên làm bằng chứng được hỗ trợ.

Một phản ví dụ liên quan là gắn `@Async` lên **factory method `@Bean`**:

~~~java
// Phản ví dụ: @Async không nên nằm trên method @Bean
@Configuration
class WrongFactoryConfig {
    @Bean
    @Async
    public ReportService reportService() {
        return new ReportService();
    }
}
~~~

Đây **không phải mã độc lập** và chưa cung cấp định nghĩa `ReportService`. `@Bean` là phương thức **tạo đối tượng để container đăng ký**; gắn `@Async` vào chính phương thức khởi tạo này không biến các phương thức nghiệp vụ của bean được trả về thành async. Hơn nữa, `@Async` quy định kiểu trả về method phải là `void` hoặc loại `Future` được hỗ trợ; ở ví dụ trên method trả `ReportService` còn không phù hợp hợp đồng đó. Hãy gắn `@Async` vào **phương thức của service được trả về**, nếu service thật sự cần xử lý nền.

### 2.3. Điều gì vẫn được phép?

| Vị trí đặt annotation | Được hỗ trợ? | Ý nghĩa |
| --- | --- | --- |
| `@Configuration` + `@EnableAsync` trên lớp cấu hình | **Có** | Bật hỗ trợ xử lý `@Async` cho application context |
| `@Bean` tạo `ThreadPoolTaskExecutor` trong lớp `@Configuration` | **Có** | Cấu hình executor được Spring quản lý |
| `@Async` trên method khai báo trong chính lớp `@Configuration` | **Không** | Không nằm trong phạm vi hỗ trợ của annotation |
| `@Async` trên method `@Bean` để cố chạy factory method nền | **Không dùng** | Không đúng trách nhiệm của bean factory method |
| `@Async` trên method của `@Service` hoặc `@Component` do Spring quản lý | **Có**, nếu qua đúng đường gọi | Method được Spring proxy/interceptor đưa sang executor |
| Một method `@Bean` trả về service có method `@Async` riêng | **Có** với service đủ điều kiện | Factory method là đồng bộ; method của **bean trả về** có thể bất đồng bộ |
| `@Async` ở cấp lớp `@Configuration` | **Không dùng để async hóa config** | Class-level `@Async` cũng không làm các method cấu hình trở thành API async được hỗ trợ |

Điểm khác biệt là **lớp khai báo method thực tế**. Nếu `AppConfig` khai báo `@Bean ReportService reportService()` và method `buildReport()` nằm trong **lớp `ReportService`**, giới hạn “method declared within `@Configuration`” không áp dụng lên `buildReport()` chỉ vì `ReportService` được tạo bởi method `@Bean`.

## 3. Vì sao hai cơ chế khác nhau?

### 3.1. Vai trò của `@Configuration` và `@Bean`

Lớp `@Configuration` diễn tả **metadata và các bean definition**. Container dùng các method `@Bean` để khởi tạo dependency, đặt tên, xác định scope và quản lý lifecycle. Với `@Configuration(proxyBeanMethods=true)` mặc định, Spring có thể **tăng cường (enhance)** lớp bằng subclass CGLIB để lời gọi giữa các method `@Bean` tuân theo ngữ nghĩa singleton/scoping.

Cơ chế tăng cường đó phục vụ **quản lý bean**, không đồng nghĩa với việc Spring `@Async` đã bao quanh các method cấu hình như các business method trên service. Một factory method bị gọi trong lúc container đang khởi tạo bean càng không nên trở thành một lời gọi nền trả về trước khi bean được tạo xong.

### 3.2. Vai trò của `@Async` và async interceptor

Khi Spring bật `@EnableAsync`, trong chế độ mặc định `AdviceMode.PROXY`, những lời gọi tới method `@Async` hợp lệ **đi qua Spring proxy** sẽ được gửi đến một `TaskExecutor`. Caller nhận kết quả theo kiểu trả về khai báo; work thực chạy ở worker thread.

~~~text
             LÚC KHỞI ĐỘNG CONTEXT
@Configuration -- @Bean --> Spring đăng ký / tạo executor và service
      |
      +-- @EnableAsync --> đăng ký async annotation processing

             LÚC GỌI NGHIỆP VỤ
Controller / caller
      |
      v
Service bean lấy từ Spring context
      |
      v
Spring proxy / async interceptor
      |
      +-- submit task --> TaskExecutor --> worker thread
      |
      +-- caller nhận void / Future / CompletableFuture
~~~

**Không có bước “Spring async hóa method trong `@Configuration`” ở sơ đồ trên.** Cấu hình chỉ **bật cơ chế và cung cấp bean**; logic nghiệp vụ nằm trong một bean riêng mà interceptor có thể xử lý đúng hợp đồng.

### 3.3. Một lớp có thể vừa là config vừa là service?

Về mặt Java, ta có thể đặt nhiều method với nhiều annotation chung một class, nhưng ở Spring bạn không nên biến lớp `@Configuration` thành nơi chứa business methods `@Async`. Lý do cốt lõi là **API `@Async` nói rõ không hỗ trợ method khai báo tại đó**. Tách responsibilities còn giúp bootstrap rõ ràng, test dễ hơn và tránh phụ thuộc vào chi tiết proxy/khởi tạo của config class.

Đặt `@EnableAsync(proxyTargetClass=true)` không giải quyết giới hạn này: thuộc tính đó chỉ thay đổi chiến lược proxy trong `PROXY` mode. Tương tự, `@Configuration(proxyBeanMethods=false)` điều chỉnh khả năng proxy của các method `@Bean`; nó **không biến** method `@Async` trong config thành trường hợp được hỗ trợ.

## 4. Cấu trúc đúng: config tạo executor, service khai báo @Async

Ví dụ kiến trúc:

~~~text
demo
├── AppConfig.java
│   ├── @Configuration
│   ├── @EnableAsync
│   └── @Bean("lessonExecutor"): ThreadPoolTaskExecutor
├── ReportService.java
│   └── @Service + @Async("lessonExecutor") trên generate()
└── AsyncConfigurationDemo.java
    └── lấy ReportService từ Spring context và gọi generate()
~~~

Executor được cấu hình **một lần**; business service do Spring quản lý. Điều quan trọng là caller **lấy bean từ context**, tránh tự `new ReportService()` rồi mong annotation được xử lý. Việc tạo service bằng `@Bean` cũng hợp lệ nếu trả về bean đúng cách; ví dụ chọn `@Service` để phân chia trách nhiệm dễ thấy.

### 4.1. Maven project chạy độc lập

Dùng **JDK 17+**, Maven và Spring Framework 6.1.3. Chương trình không cần Spring Boot server; Spring Framework thuần đủ để minh họa proxy.

Cấu trúc file:

~~~text
async-config-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                ├── AppConfig.java
                ├── ReportService.java
                └── AsyncConfigurationDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-config-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.3</version>
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
                    <mainClass>demo.AsyncConfigurationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Dependency `spring-context` kéo theo các dependency Spring cần cho `@EnableAsync`, AOP và `ThreadPoolTaskExecutor` trong ví dụ. Ứng dụng Spring Boot thực tế nên để BOM/parent quản lý các phiên bản Spring thống nhất.

### 4.2. Cấu hình trong `AppConfig.java`

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AppConfig {

    @Bean("lessonExecutor")
    public ThreadPoolTaskExecutor lessonExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("lesson-");
        return executor;
    }
}
~~~

`@EnableAsync` nằm **đúng chỗ**, trên class cấu hình. `@Bean` tạo một `ThreadPoolTaskExecutor` được Spring container quản lý. Đáng chú ý: **không có `@Async` trên method `lessonExecutor()`**; method này chỉ tạo và cấu hình executor.

Ở đây pool nhỏ để minh họa, không phải thông số mặc định nên dùng trong production. Trong dự án thực tế hãy cấu hình số worker, queue, rejection và shutdown theo workload.

### 4.3. Business method trong `ReportService.java`

~~~java
package demo;

import java.util.Locale;
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("lessonExecutor")
    public CompletableFuture<String> generate(String name) {
        boolean onWorker =
                Thread.currentThread().getName().startsWith("lesson-");

        String value = name.toUpperCase(Locale.ROOT)
                + "|worker=" + onWorker;

        return CompletableFuture.completedFuture(value);
    }
}
~~~

Chính method `generate` nằm trên **`ReportService`**, một bean độc lập với `AppConfig`. `@Async("lessonExecutor")` chọn executor có tên `lessonExecutor`. Ta đặt tiền tố thread để kiểm tra method đã chạy ở worker thread được cấu hình.

**Tại sao target method trả `CompletableFuture.completedFuture(...)`?** Với `@Async`, Spring proxy nộp lời gọi của method vào executor và trả một `CompletableFuture` đại diện cho việc thực thi ở mức proxy. Method trong target thực sự chạy trên worker có thể trả một future tạm thời đã hoàn tất. Điều đó **không** có nghĩa caller đã tự chạy target method đồng bộ. Spring sẽ lấy kết quả của target method qua cơ chế interceptor.

### 4.4. Bootstrap trong `AsyncConfigurationDemo.java`

~~~java
package demo;

import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class AsyncConfigurationDemo {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AppConfig.class,
                             ReportService.class)) {

            ReportService service = context.getBean(ReportService.class);

            String result =
                    service.generate("spring").get(5, TimeUnit.SECONDS);

            System.out.println(result);
        }
    }
}
~~~

Trong thư mục `async-config-demo` chạy:

~~~bash
mvn -q compile exec:java
~~~

Đầu ra do chương trình Java in (không tính log build nếu Maven/plugin có hiển thị):

~~~text
SPRING|worker=true
~~~

**Vì sao output đáng tin?** Chương trình tạo một bean executor có tiền tố thread `lesson-`, lấy `ReportService` **từ Spring context** (nên có async interception), gọi method annotated `@Async("lessonExecutor")`, rồi chờ future bằng `get(5, TimeUnit.SECONDS)`. Trong task, thread hiện tại có tên bắt đầu bằng tiền tố đó, nên phần `worker=true` được hình thành tại **worker**. `get` chờ kết quả và có timeout để bài demo không chờ vô hạn nếu xảy ra lỗi.

Với môi trường quá chậm, `get(5, ...)` có thể ném `TimeoutException`; đó là lỗi timing/bất khả dụng cần điều tra, không phải dòng output thứ hai. Khi tự tạo context trong `main`, `try-with-resources` đóng context và cho container dọn dẹp executor bean; **không tự gọi `shutdown()` bên trong `generate`**.

Ví dụ này có ba Java file được biên dịch cùng package. Các phản ví dụ ở phần 2 là fragment phân tích **không** thuộc project này.

## 5. Phân biệt ba vấn đề thường bị trộn lẫn

### 5.1. Giới hạn đặc biệt của `@Configuration`

**Quy tắc:** Method được **khai báo bên trong `@Configuration`** không được Spring `@Async` hỗ trợ. Đây là điều kiện theo **loại lớp chứa declaration**, chứ không phải chỉ do caller quên dùng proxy.

**Cách sửa:** Di chuyển method nghiệp vụ sang một service/component bean, giữ `@Configuration` để bật `@EnableAsync` và định nghĩa executor/dependency. Gọi service đó qua Spring proxy.

### 5.2. Self-invocation trên một bean thường

Ngay cả trên một class `@Service` đủ điều kiện, lời gọi từ method này sang method khác **trong cùng instance** cũng thường bỏ qua Spring proxy khi dùng `AdviceMode.PROXY` mặc định.

~~~java
@Service
public class DataService {
    public void start() {
        calculate(); // this.calculate(), không đi qua proxy
    }

    @Async
    public void calculate() {
        // Không được chuyển thread khi gọi trực tiếp từ start() như trên.
    }
}
~~~

Đây là **fragment minh họa**, cần import `Service` và `Async`; không phải chương trình độc lập. Khác với giới hạn `@Configuration`, method `calculate()` ở đây *có thể được hỗ trợ* khi một bean khác gọi qua **proxy `DataService`**. Cách sửa thông thường là tách lời gọi sang bean khác và inject service đã được Spring quản lý, hoặc thiết kế interface cho async boundary.

Với self-invocation của service bình thường, Spring còn có `AdviceMode.ASPECTJ` và weaving như một lựa chọn nâng cao. Nó cần dependency/cấu hình riêng và không nên được coi là lý do giữ business `@Async` trong `@Configuration`.

### 5.3. Lifecycle và khởi tạo bean

Đừng đặt `@Async` trực tiếp lên `@PostConstruct` và kỳ vọng nó chạy nền: tài liệu Spring ghi rõ hai cơ chế không được kết hợp. Lúc khởi tạo bean, proxy và dependencies có thể chưa sẵn sàng để thực hiện lời gọi bất đồng bộ theo thiết kế.

Nếu cần warm-up hoặc xử lý sau startup, để **một bean khởi tạo khác** nhận lifecycle/event rồi gọi method `@Async` trên **bean service** được inject. Với Spring Boot có thể dùng listener `ApplicationReadyEvent` khi việc đó thực sự phải bắt đầu sau khi ứng dụng sẵn sàng; chọn event và chính sách lỗi theo nhu cầu ứng dụng. Không tự gọi một async method trong constructor hoặc `@PostConstruct` của chính đối tượng đó rồi mong proxy can thiệp.

### Bảng chẩn đoán

| Dấu hiệu | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `@Async` đặt trên method trong `@Configuration` | Method thuộc vùng không được hỗ trợ | Chuyển sang service bean |
| Method `@Async` của service vẫn chạy ở caller | Self-invocation, object tạo bằng `new`, chưa bật `@EnableAsync` hoặc proxy không được đi qua | Lấy bean từ Spring context, gọi qua proxy, kiểm tra cấu hình |
| `@Async("name")` không dùng đúng thread pool | Executor bean sai tên/qualifier hoặc cấu hình khác | Kiểm tra `@Bean("name")`, injection và thread prefix |
| Method `@Async` bị lỗi trong khi chạy | Exception trong task và cách nhận lỗi qua `Future`/`CompletableFuture` | Theo dõi future hoặc `AsyncUncaughtExceptionHandler` nếu `void` |
| Async method bị từ chối trước khi chạy | Executor quá tải/đã shutdown | Xử lý `TaskRejectedException` ở điểm submit, kiểm tra queue và lifecycle |
| Gọi async trong quá trình dựng bean | Lifecycle chưa phù hợp | Gọi từ bean khác sau khi context sẵn sàng |

## 6. Kiểu trả về và xử lý lỗi của @Async

Spring `@Async` hỗ trợ các phương thức có kiểu trả về `void` hoặc một `Future` hợp lệ, bao gồm `CompletableFuture<T>`. Những method muốn trả dữ liệu nghiệp vụ nên dùng `CompletableFuture<T>` để caller có thể chờ, ghép kết quả và xử lý lỗi.

~~~java
// Fragment trong @Service với async proxy và executor đã cấu hình.
@Async("lessonExecutor")
public CompletableFuture<Integer> calculate(int x) {
    if (x < 0) {
        throw new IllegalArgumentException("x must be non-negative");
    }
    return CompletableFuture.completedFuture(x * 2);
}
~~~

Đây là **fragment**, không phải class độc lập. Nếu task được nhận nhưng ném exception trong worker, `CompletableFuture` mà caller nhận có thể hoàn tất thất bại. Caller dùng `get()` để nhận `ExecutionException` (kiểm tra cause) hoặc `join()` để nhận `CompletionException`; cần tôn trọng interrupt khi dùng `get()`.

~~~java
// Fragment trong caller, method khai báo throws InterruptedException.
CompletableFuture<Integer> future = service.calculate(21);
try {
    System.out.println(future.get()); // 42
} catch (java.util.concurrent.ExecutionException ex) {
    System.err.println("Task failed: " + ex.getCause());
}
~~~

Không dùng `@Async` trên method trả trực tiếp `String`/`int` và mong Spring tự bọc giá trị như một Future; đó không phải kiểu trả về được hỗ trợ theo hợp đồng annotation.

Với method `@Async void`, caller không có Future để nhận lỗi từ worker. Spring cho phép cấu hình `AsyncUncaughtExceptionHandler` qua `AsyncConfigurer`; mặc định lỗi thường được log. Trong ứng dụng production, đừng để các tác vụ quan trọng thất bại mà không có cơ chế quan sát/truyền trạng thái.

Một lỗi khác xảy ra **ngay lúc nộp task**: executor có thể ném `TaskRejectedException` nếu pool quá tải hoặc shutdown. Khi điều đó xảy ra, chưa có công việc đã được nhận; riêng `future.exceptionally(...)` không thay cho catch rejection ở ranh giới caller. Cấu hình queue/backpressure và chính sách xử lý quá tải là phần riêng của thiết kế async.

## 7. Refactor an toàn: từ cấu hình trộn nghiệp vụ sang hai bean

Giả sử project cũ có method nghiệp vụ `sendInvoice()` bên trong `@Configuration` và gắn `@Async`. Cách sửa theo thứ tự:

1. **Đặt lại trách nhiệm:** Giữ `@Configuration` để định nghĩa bean và `@EnableAsync`. Di chuyển xử lý gửi hóa đơn sang `InvoiceSender` hoặc một service phù hợp.
2. **Giữ hợp đồng dữ liệu:** Method ở service dùng `CompletableFuture<Result>` khi cần kết quả, hoặc `void` nếu thật sự fire-and-forget và có xử lý lỗi riêng. Không đổi chữ ký public một cách tùy tiện.
3. **Định nghĩa executor:** Tạo/reuse `ThreadPoolTaskExecutor` bean có tên ổn định, sizing và rejection phù hợp với tải.
4. **Đổi nơi gọi:** Caller inject `InvoiceSender` do Spring quản lý; không tạo bằng `new`, không giữ lời gọi tự chạy trong config class.
5. **Kiểm tra transaction/context:** Transaction/MDC/security context của thread gọi không tự nhiên được chia sẻ sang worker. Truyền dữ liệu cần thiết, cấu hình context propagation và transaction tại ranh giới thích hợp.
6. **Test đúng hành vi:** Kiểm tra thread thực thi bằng thread prefix/ID của worker, quan sát kết quả Future và kiểm tra lỗi khi pool từ chối.
7. **Giữ logic sau startup rõ ràng:** Nếu công việc phải chạy khi khởi động, một initializer/event listener khác gọi service qua proxy sau thời điểm phù hợp.

### Phác thảo trước và sau

**Trước — cách không được hỗ trợ:**

~~~java
@Configuration
@EnableAsync
public class InvoiceConfig {
    @Async
    public CompletableFuture<String> sendInvoice() {
        return CompletableFuture.completedFuture("sent");
    }
}
~~~

**Sau — cách được hỗ trợ:**

~~~java
@Configuration
@EnableAsync
public class InvoiceConfig {
    // @Bean executor và các dependency cấu hình khác.
}

// Trong một file riêng, class do Spring quản lý:
@Service
public class InvoiceSender {
    @Async("invoiceExecutor")
    public CompletableFuture<String> sendInvoice() {
        return CompletableFuture.completedFuture("sent");
    }
}
~~~

Hai đoạn trên là **phác thảo kiến trúc**: cần import annotation, bean executor có tên `invoiceExecutor` và caller đi qua proxy. Ví dụ project Maven ở phần 4 mới là chương trình hoàn chỉnh có thể chạy nguyên trạng.

### Trường hợp service được tạo từ `@Bean`

Bạn **không bị bắt buộc** dùng `@Service` cho mọi service. Ví dụ:

~~~java
@Configuration
@EnableAsync
class InvoiceBeans {
    @Bean
    InvoiceSender invoiceSender() {
        return new InvoiceSender();
    }

    @Bean("invoiceExecutor")
    ThreadPoolTaskExecutor invoiceExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        return executor;
    }
}
~~~

Đây là **fragment cấu hình**, cần import và lớp `InvoiceSender` với method `@Async` nằm trong **lớp riêng**. `InvoiceSender` do Spring quản lý vì được trả từ `@Bean`; sau khi container xử lý bean, async proxy có thể áp dụng lên method của đối tượng đó. **Factory method `invoiceSender()` không cần `@Async`.**

Tách lớp theo trách nhiệm là điều kiện quan trọng; cách đăng ký bean (`@Service` hay `@Bean`) là lựa chọn cấu hình.

## 8. Những hiểu lầm thường gặp

1. **“`@EnableAsync` trên `@Configuration` là sai vì không được dùng async trong cấu hình.”** Sai. Spring khuyến nghị bật `@EnableAsync` trong `@Configuration`; giới hạn chỉ dành cho **`@Async` trên methods khai báo ở đó**.
2. **“`@Async` trên method `@Bean` làm bean được tạo bất đồng bộ.”** Sai cách dùng. `@Bean` phục vụ vòng đời tạo bean; xử lý nghiệp vụ async ở method của service bean.
3. **“Có thể đổi `proxyBeanMethods=false` để `@Async` trong config hoạt động.”** Không. Tùy chọn này thay đổi interception của `@Bean`, không biến config method thành async method được hỗ trợ.
4. **“Bật `proxyTargetClass=true` là đã xử lý toàn bộ vấn đề.”** Không. Nó chỉ thay loại proxy; không thay hợp đồng của `@Async` với `@Configuration`.
5. **“Nếu service được tạo bởi `@Bean` thì method `@Async` của service cũng bị cấm.”** Sai. Giới hạn dựa trên **nơi method được khai báo**; bean trả về có thể được Spring xử lý như những bean khác.
6. **“Method `@Async` trong `@Service` luôn chạy nền, kể cả khi gọi `this.method()`.”** Sai trong proxy mode mặc định: self-invocation không đi qua proxy.
7. **“`@Async` hoạt động tự động trên object tạo bằng `new`.”** Không. Bean cần đi qua cơ chế quản lý/proxy hoặc weaving được cấu hình.
8. **“Bật `@EnableAsync` là mọi tác vụ đều được xử lý tốt bất kể executor.”** Không. Hàng đợi, số worker, timeout, rejection, dữ liệu và lỗi vẫn phải được thiết kế.
9. **“Future trả về có nghĩa method chạy đồng bộ.”** Không. Proxy có thể trả Future đại diện cho task; method trong worker có thể tạo một completed future để chứa kết quả thực.
10. **“Lỗi trong task và lỗi từ chối lúc gửi là cùng một đường.”** Không. Rejection có thể ném trước khi trả Future, còn lỗi trong worker đi vào Future hoặc handler theo loại return.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Có thể viết `@Configuration @EnableAsync` trong cùng class không?  
**Trả lời:** Có. `@EnableAsync` được dùng trên class cấu hình để bật asynchronous annotation processing.

**Câu 2.** Có thể đặt `@Async` trên method `generate()` được khai báo trực tiếp trong `@Configuration` rồi bảo đảm nó chạy background không?  
**Trả lời:** Không. Spring Javadoc nói rõ method trong `@Configuration` không được `@Async` hỗ trợ.

**Câu 3.** Nếu `@Bean` trong config trả về `ReportService`, còn `ReportService.generate()` có `@Async`, giới hạn có áp dụng không?  
**Trả lời:** Không theo cách đó; `generate()` được khai báo ở `ReportService`. Bean phải được Spring quản lý và lời gọi đi qua async proxy để interception xảy ra.

**Câu 4.** Một `@Service` gọi `this.calculateAsync()` trong chính class. Vì sao có thể chạy đồng bộ?  
**Trả lời:** Với `AdviceMode.PROXY`, lời gọi nội bộ không đi qua proxy. Gọi method qua bean proxy từ lớp khác.

**Câu 5.** Tại sao Spring có CGLIB proxy cho `@Configuration` mà method trong đó vẫn không nên gắn `@Async`?  
**Trả lời:** CGLIB enhancement của config xử lý `@Bean`/scope. Nó không thay đổi quy định hỗ trợ của annotation `@Async` trên method khai báo trong config.

**Câu 6.** Muốn làm warm-up bất đồng bộ sau khi ứng dụng sẵn sàng, cần tổ chức ra sao?  
**Trả lời:** Dùng một bean initializer/listener phù hợp, gọi method `@Async` trên bean service khác qua Spring proxy; không trực tiếp dùng `@Async` trên `@PostConstruct` hoặc method trong `@Configuration`.

## 10. Tài liệu tham khảo chính thức

- [Spring Framework 6.2.7 — Async Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/scheduling/annotation/Async.html): quy định rõ `@Async` không hỗ trợ phương thức khai báo trong lớp `@Configuration`; kiểu trả về `void`/`Future`/`CompletableFuture`.
- [Spring Framework 5.3.36 — Async Javadoc](https://docs.spring.io/spring-framework/docs/5.3.36/javadoc-api/org/springframework/scheduling/annotation/Async.html): xác nhận giới hạn trên cũng có ở nhánh 5.3.
- [Spring Framework 6.1.11 — EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): cách đặt `@EnableAsync` trên `@Configuration`, chế độ proxy và self-invocation.
- [Spring Framework 6.1.3 — Configuration Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/context/annotation/Configuration.html): `@Bean`, config class enhancement, `proxyBeanMethods` và bootstrapping.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableAsync`, `@Async`, chọn executor, kiểu trả về và xử lý exception.
