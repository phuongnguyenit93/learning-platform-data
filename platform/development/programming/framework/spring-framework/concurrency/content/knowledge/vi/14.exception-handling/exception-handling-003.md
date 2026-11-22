# AsyncUncaughtExceptionHandler cho phương thức @Async trả về void

> **Module:** Spring Framework – concurrency  
> **Chủ đề cha:** Xử lý ngoại lệ  
> **Mục tiêu:** Hiểu vì sao exception phát sinh trong một phương thức `@Async` trả về `void` không quay lại caller theo cách thông thường; biết cấu hình `AsyncUncaughtExceptionHandler`, quan sát thông tin `Throwable`/`Method`/`params`, phân biệt với `Future`/`CompletableFuture` và xử lý lỗi nộp task, đồng thời thiết kế logging/metrics đáng tin cậy.

## 1. Vấn đề nền tảng: @Async void không có Future để trả lỗi

Xét một service Spring:

~~~java
@Service
public class NotificationService {
    @Async
    public void sendNotification(String orderId) {
        throw new IllegalStateException("notification service unavailable");
    }
}
~~~

Đây là **đoạn tích hợp Spring**, cần import `@Service` và `@Async`, bật async processing và gọi qua Spring proxy; chưa phải chương trình độc lập. Khi lời gọi thực sự đi qua advice của `@Async` và task được executor chấp nhận, luồng caller thường nhận quyền điều khiển **trước khi** thân phương thức hoàn tất. Nếu thân phương thức ném `IllegalStateException` trong worker, caller không thể viết một `try/catch` ngay quanh lệnh `sendNotification(...)` để bắt exception đó như một lệnh gọi đồng bộ.

Không có `Future` trả về từ một phương thức `void`; do đó caller **không có handle kết quả** để gọi `get()`, `join()` hay kiểm tra trạng thái lỗi của task. Spring cung cấp `org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler` để xử lý những exception **không được bắt trong thân phương thức `@Async void`**.

Ý tưởng chính:

- **Caller:** gửi yêu cầu chạy một phương thức async, không nhận giá trị kết quả qua signature `void`.
- **Executor:** nhận và chạy công việc sau đó, trên một thread phù hợp với chính sách scheduling.
- **Worker:** khi công việc ném `Throwable` chưa xử lý, async interceptor đưa lỗi đến `AsyncUncaughtExceptionHandler`.
- **Handler:** nhận error, method và arguments; ghi nhận, cảnh báo hoặc phát tín hiệu quan sát. Handler **không biến `void` thành `Future`** và không tự gửi exception về caller.

Cơ chế này chỉ áp dụng cho lời gọi thực sự được interception. Nếu `@Async` bị bỏ qua (chẳng hạn self-invocation trong chế độ proxy mặc định), phương thức có thể chạy đồng bộ và exception lại đi theo stack thông thường.

## 2. Luồng thực thi và hai thời điểm có thể thất bại

~~~text
Caller thread
   |
   | gọi notificationService.sendNotification("ref-42")
   v
Spring @Async proxy / interceptor
   |
   +-- lỗi khi nộp task / executor shutdown hoặc reject?
   |       |
   |       +--> caller có thể nhận TaskRejectedException ngay tại lời gọi
   |
   +-- executor CHẤP NHẬN
           |
           +--> lời gọi void của caller kết thúc (thường chưa có kết quả)
           |
           v
       Thread thực thi task
           |
           +-- sendNotification chạy thành công --> hoàn tất
           |
           +-- sendNotification ném exception chưa bắt
                    |
                    v
             AsyncUncaughtExceptionHandler
               handleUncaughtException(error, method, params)
                    |
                    +--> log / metric / cảnh báo / báo lỗi có kiểm soát
                    +--> KHÔNG tự truyền Throwable về caller
~~~

**Hai đường lỗi phải được phân biệt:**

1. **Lỗi nộp task:** `TaskRejectedException` của Spring (hoặc rejection exception phù hợp theo executor) xảy ra **khi proxy cố nộp** vào executor đã đóng/bão hòa. Đây là lỗi của quá trình lên lịch, có thể quan sát ngay ở caller. Nó **không phải** exception được ném bởi thân phương thức async và không được bảo đảm đi qua `AsyncUncaughtExceptionHandler`.
2. **Lỗi khi task đã chạy:** exception được ném từ thân phương thức `@Async void` trong giai đoạn thực thi. Spring dùng handler để xử lý, bởi không có `Future` cho caller quan sát.

Nếu executor sử dụng chính sách đặc biệt như `CallerRunsPolicy` lúc quá tải, task có thể chạy trên caller thread; đừng suy luận vị trí thread chỉ từ tên `@Async`. Tuy nhiên đường xử lý exception của proxy cho phương thức `void` vẫn cần hiểu theo hợp đồng handler.

## 3. AsyncUncaughtExceptionHandler là interface gì?

Interface nằm ở package:

~~~java
org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler
~~~

Chữ ký quan trọng (viết rút gọn để học, không phải một class Java độc lập):

~~~java
void handleUncaughtException(
    Throwable exception,
    java.lang.reflect.Method method,
    Object... params);
~~~

Ý nghĩa các tham số:

| Tham số | Đại diện cho | Lưu ý |
| --- | --- | --- |
| `Throwable exception` | Lỗi không được xử lý từ phương thức `@Async void` | Có thể là `RuntimeException`, hoặc `Error`; không mặc định chuyển thành `ExecutionException` |
| `Method method` | Reflection metadata về phương thức async được gọi | Có thể lấy `getName()`, `getDeclaringClass()`; không nên giả định Method luôn thuộc đúng class proxy cụ thể |
| `Object... params` | Các đối số của lời gọi gốc, theo thông tin Spring interceptor chuyển vào | Có thể chứa dữ liệu nhạy cảm, object mutable, collection lớn hoặc `toString()` nguy hiểm |

Một handler thường cần trả lời ba câu hỏi: **phương thức nào lỗi? lỗi gì? cần báo động/ghi nhận thế nào?** Đó không đồng nghĩa với “retry ngay” hoặc “đảo ngược mọi tác dụng phụ đã xảy ra”.

Ví dụ handler gọn:

~~~java
AsyncUncaughtExceptionHandler handler = (error, method, args) -> {
    logger.error("Async void method {} failed", method.getName(), error);
    failedTasksCounter.increment();
};
~~~

Đây là **snippet tích hợp**, yêu cầu ứng dụng đã có `logger` và `failedTasksCounter`. Nó không in toàn bộ `args`, vì argument có thể chứa token, email, thông tin cá nhân, dữ liệu giao dịch hoặc đối tượng có khả năng sinh log rất lớn.

## 4. Handler mặc định là gì nếu không cấu hình?

Khi xử lý phương thức `@Async` trả `void` mà ứng dụng không cung cấp exception handler riêng, Spring Framework dùng cơ chế mặc định với `SimpleAsyncUncaughtExceptionHandler`. Handler mặc định **ghi log lỗi** của phương thức async; nó không tự retry, không tự báo lỗi về HTTP caller và không đưa kết quả vào một future.

Điều này có một hệ quả sản phẩm quan trọng: **có log lỗi không đồng nghĩa hệ thống đã xử lý lỗi nghiệp vụ**. Nếu công việc là gửi email, tạo invoice hay đồng bộ hệ thống khác, chỉ logging chưa thể cho biết task có cần chạy lại hay không, đã phát sinh side effect nào và có cần cảnh báo vận hành không.

Nếu log aggregation không thu thập đúng logger/severity, lỗi của `@Async void` có thể bị bỏ qua trong quá trình vận hành. Vì thế handler chuyên dụng nên phát ra metric và correlation ID an toàn, đồng thời có runbook giải quyết task lỗi.

## 5. Cấu hình handler qua AsyncConfigurer

Cách chính thống với annotation-based async trong Spring là cung cấp `org.springframework.scheduling.annotation.AsyncConfigurer` trong cấu hình có `@EnableAsync`, rồi override `getAsyncUncaughtExceptionHandler()`.

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration implements AsyncConfigurer {
    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, args) -> {
            // Ghi nhận lỗi của @Async void tại đây.
        };
    }
}
~~~

Đây là **mã minh họa tích hợp**; phải import các kiểu và để Spring nạp configuration. Một `AsyncConfigurer` đủ để cấu hình default exception handler cho việc xử lý `@Async` trong context tương ứng. Tránh đăng ký nhiều `AsyncConfigurer` cạnh tranh trong cùng context; cần một cấu hình mặc định xác định được.

`AsyncConfigurer` có hai thành phần cần phân biệt:

- `getAsyncExecutor()`: **tuỳ chọn** cung cấp executor mặc định cho `@Async`; khi không cung cấp, Spring thực hiện cơ chế chọn executor theo type/name và fallback tương ứng.
- `getAsyncUncaughtExceptionHandler()`: **tuỳ chọn** cung cấp handler cho exception không được bắt trong các method `@Async` trả `void`.

Không nhất thiết phải override cả hai. Ví dụ đầy đủ ở mục 8 **chỉ override handler** nhưng vẫn khai báo một `ThreadPoolTaskExecutor` làm bean cho Spring chọn.

**Lưu ý lifecycle:** class triển khai `AsyncConfigurer` được khởi tạo tương đối sớm trong quá trình cấu hình async. Nếu handler cần dependency phức tạp, tránh kích hoạt sớm bean chưa hoàn chỉnh; dùng cấu hình rõ ràng/lazy lookup khi thích hợp. Chỉ khai báo một bean tùy ý có type `AsyncUncaughtExceptionHandler` không đồng nghĩa mọi interceptor tự động dùng bean đó; đường cấu hình được đề cập ở đây là `AsyncConfigurer`.

## 6. Khi nào handler được gọi, và khi nào không?

| Tình huống | AsyncUncaughtExceptionHandler có phải đường xử lý chính? | Vì sao |
| --- | --- | --- |
| `@Async public void run()` ném exception chưa bắt khi thực thi | **Có** | Caller không có Future để lấy lỗi |
| `@Async public void run()` tự `try/catch` và không ném lại | **Không** | Không còn exception chưa được xử lý |
| `@Async public Future<T> run()` bị lỗi khi task chạy | **Không** | Lỗi được biểu diễn qua Future kết quả |
| `@Async public CompletableFuture<T> run()` bị lỗi khi task chạy | **Không** | Lỗi được biểu diễn qua CompletableFuture kết quả |
| `@Async public CompletableFuture<Void> run()` ném exception | **Không** | Dù không có giá trị hữu ích, method vẫn có Future để quan sát |
| `@Async void` bị từ chối lúc submit | **Không đảm bảo** | Lỗi có thể ném từ proxy ngay tại lời gọi của caller |
| `@Async` bị bỏ qua bởi self-invocation | **Không** | Không đi qua interceptor để gửi đến handler |
| `@Async void` khởi động future riêng, future ấy lỗi về sau | **Không mặc định** | Lỗi xảy ra ở một job detached; method void có thể đã kết thúc thành công |
| Code chạy bằng `executor.execute(() -> ...)` trực tiếp, không `@Async` | **Không mặc định** | Nó không đi qua `@Async` interceptor của Spring |

Bảng này cũng giải thích vì sao viết **`@Async void` cho task cần được caller theo dõi là lựa chọn thiếu thông tin**. Nếu caller cần biết task đã hoàn tất, thành công hay thất bại, nên cân nhắc trả `CompletableFuture<Void>` thay vì `void`.

## 7. Đối chiếu: @Async void với @Async CompletableFuture<Void>

Ví dụ hai API cùng thực hiện một công việc không có giá trị trả về:

~~~java
@Async
public void sendFireAndForget(String id) {
    sendToExternalService(id);
}

@Async
public CompletableFuture<Void> sendTracked(String id) {
    sendToExternalService(id);
    return CompletableFuture.completedFuture(null);
}
~~~

Đây là **snippet tích hợp Spring** với `sendToExternalService` là hàm nghiệp vụ giả định; không phải tệp Java độc lập.

- Với `sendFireAndForget`, exception chưa bắt ở worker đi đến `AsyncUncaughtExceptionHandler`. Caller không thể await bằng API đã khai báo.
- Với `sendTracked`, Spring trả một `CompletableFuture<Void>` cho caller. Caller có thể gọi `whenComplete`/`exceptionally` hoặc `get()`/`join()` để quan sát kết quả. Nếu có exception trong task, caller nhìn thấy exceptional completion; handler dành cho void **không được dùng** cho lỗi này.
- `CompletableFuture<Void>` không có payload nghiệp vụ, nhưng vẫn có **trạng thái completion**. Không nhầm “Void” generic type với “void” return type.
- Nếu một phương thức `@Async` tự gọi một API async khác và trả `CompletableFuture` đã hoàn tất trước khi API con thực sự hoàn thành, caller có thể nhận tín hiệu thành công quá sớm. Contract phải đại diện đúng vòng đời toàn bộ công việc mà bạn muốn theo dõi.

Một lỗi thường gặp là chuyển method từ `void` sang `CompletableFuture<Void>` nhưng không cập nhật nơi quan sát future. Khi đó exception vẫn có thể bị bỏ sót, chỉ là chuyển từ handler sang một future không ai kiểm tra.

## 8. Ví dụ Spring Framework 6.2.9 + Java 17 chạy được

Bài thực hành tạo `@Async void` service ném `IllegalStateException`; một `AsyncConfigurer` đưa lỗi tới handler tùy chỉnh. `CountDownLatch` cho phép CLI đợi handler hoàn tất, nhờ đó **thứ tự stdout xác định**, không cần đoán lúc thread chạy.

Cấu trúc project:

~~~text
spring-void-handler-demo/
├── pom.xml
└── src/main/java/demo/VoidAsyncHandlerDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-void-handler-demo</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/VoidAsyncHandlerDemo.java**:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class VoidAsyncHandlerDemo implements AsyncConfigurer {
    private static final CountDownLatch HANDLED = new CountDownLatch(1);

    @Bean("taskExecutor")
    public ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(4);
        pool.setThreadNamePrefix("demo-async-");
        return pool;
    }

    @Bean
    public NoticeService noticeService() {
        return new NoticeService();
    }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, args) -> {
            try {
                System.out.println("Method: " + method.getName());
                System.out.println("Error: " + error.getClass().getSimpleName()
                    + ": " + error.getMessage());
                System.out.println("Arguments: " + args.length);
            } finally {
                HANDLED.countDown();
            }
        };
    }

    public static class NoticeService {
        @Async
        public void sendNotice(String reference) {
            throw new IllegalStateException("delivery failed");
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(VoidAsyncHandlerDemo.class)) {
            context.getBean(NoticeService.class).sendNotice("ref-42");
            if (!HANDLED.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Handler was not called");
            }
            System.out.println("Caller: no task exception propagated");
        }
    }
}
~~~

Chạy từ thư mục `spring-void-handler-demo` (JDK 17+, Maven):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.VoidAsyncHandlerDemo
~~~

**Các dòng stdout của chương trình**:

~~~text
Method: sendNotice
Error: IllegalStateException: delivery failed
Arguments: 1
Caller: no task exception propagated
~~~

Tác vụ được Spring lên lịch trên executor với tên `taskExecutor`; nó ném exception và handler nhận `Method`, `Throwable` cùng mảng một đối số. `HANDLED.countDown()` chạy trong `finally` của handler, bảo đảm `main` chỉ in dòng cuối sau khi handler đã in ba dòng trước. Đây là demo có đầu ra xác định trong điều kiện executor nhận task và handler chạy trong hạn năm giây; nếu quá chậm, chương trình chủ động báo timeout.

Ví dụ đã được **biên dịch với mục tiêu Java 17 và thực thi thành công** trên một JDK mới hơn; stdout thực tế khớp bốn dòng trên. Lệnh Maven vẫn có thể in các thông báo môi trường khác từ dependency/plugin, nhưng đó không phải bốn dòng `System.out.println` của chương trình.

**Tại sao bài không override `getAsyncExecutor()`?** `AsyncConfigurer` cho phép chỉ cung cấp handler. Spring vẫn giải quyết default executor từ bean `ThreadPoolTaskExecutor` duy nhất (đồng thời được đặt tên `taskExecutor`). Đây chính là cách cấu hình riêng xử lý lỗi mà không phải tự tạo thêm một executor khác.

**Điểm giới hạn:** ví dụ cố ý ném lỗi; không có gửi thông báo thật hay lưu trạng thái vào DB. `CountDownLatch` chỉ dùng để kiểm thử/CLI đợi minh họa, không phải chiến lược bảo đảm delivery cho một HTTP API production.

## 9. Cách implement handler dành cho production

Handler không phải nơi nên xử lý lại toàn bộ nghiệp vụ nặng. Nó cần **nhanh, an toàn và không gây lỗi thứ cấp**, vì thường đang chạy trên thread thực thi tác vụ hoặc đường hoàn tất của executor.

Một handler khả dụng trong ứng dụng thực tế nên:

1. **Ghi log có cấu trúc:** tên class/method, loại exception, message được kiểm soát, correlation ID/operation ID không nhạy cảm. Dùng logger với stack trace khi chính sách logging cho phép.
2. **Tăng metric lỗi:** ví dụ `async_void_failure_total` gắn tag giới hạn cardinality theo tên method và loại lỗi; tránh dùng raw order ID làm tag metric.
3. **Không in nguyên mảng params:** argument có thể là access token, email, dữ liệu người dùng, `MultipartFile` hoặc object graph khổng lồ. `toString()` còn có thể ném lỗi hoặc thực hiện công việc bất ngờ.
4. **Phân biệt loại lỗi:** lỗi validation, network, timeout, bug logic, reject, shutdown; không auto-retry mọi exception.
5. **Ghi nhận trạng thái nghiệp vụ qua cơ chế đáng tin cậy:** nếu công việc quan trọng, handler có thể phát một event lỗi có idempotency key hoặc yêu cầu cập nhật job record, nhưng phải xem xét transaction và độ tin cậy của kênh ghi.
6. **Không thực hiện I/O blocking kéo dài trong handler:** nếu handler bị kẹt, worker vẫn chưa được giải phóng; pool có thể bị giảm throughput hoặc thêm overload.
7. **Tự bảo vệ lỗi thứ cấp:** dùng minimal operations và biện pháp catch phù hợp quanh logging/notification. Không để handler ném thêm exception ngoài ý muốn rồi nghĩ rằng Spring đã tự sửa mọi việc.
8. **Quan sát cả đường submit:** dùng metric `TaskRejectedException` riêng vì một task bị reject có thể chưa từng gọi đến handler.

Mẫu pseudo-logging tối giản để trình bày nguyên tắc:

~~~java
@Override
public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
    return (error, method, args) -> {
        try {
            metrics.incrementAsyncFailure(
                method.getDeclaringClass().getSimpleName(),
                method.getName(),
                error.getClass().getSimpleName());
            log.error("Unhandled @Async void failure in {}",
                method.getName(), error);
        } catch (RuntimeException loggingFailure) {
            // Fallback tối thiểu theo chính sách hệ thống.
        }
    };
}
~~~

Đây là **đoạn tích hợp**, giả định có dependency `metrics` và `log`, không phải chương trình biên dịch độc lập. Trong production, không nên âm thầm nuốt `loggingFailure` mà không có kênh báo lỗi dự phòng; cần chọn kênh có thể vận hành an toàn và tránh chính nó làm tràn log hoặc nghẽn executor.

## 10. Handler không phải cơ chế retry tự động

`AsyncUncaughtExceptionHandler` được gọi sau khi một task `@Async void` đã thất bại. Nó **không lưu lại đầy đủ một command bền vững**, không bảo đảm sự kiện chỉ xảy ra một lần, không có `Future` để biết caller đã đi đâu và không hoàn tác các side effect đã thực hiện trước khi exception.

Không làm như sau:

~~~java
return (error, method, args) -> {
    method.invoke(targetBean, args);  // Nguy hiểm: retry bằng reflection ngay
};
~~~

Đây là **phản ví dụ**, không độc lập vì biến `targetBean` chưa khai báo. Nó có thể:

- Gọi sai instance/proxy và bỏ qua advice hoặc gây recursion;
- Nhân tác dụng phụ khi task đã ghi DB/gửi request trước khi lỗi;
- Retry tức thời trong lúc dependency vẫn quá tải;
- Gây lỗi reflection, security, transaction, context hoặc duplicate.

Nếu cần retry, thiết kế **ngay từ công việc nghiệp vụ**: operation ID, idempotency key, dữ liệu đầu vào bền vững, phân loại lỗi, `maxAttempts`, backoff + jitter, deadline, queue/job store và trạng thái terminal rõ ràng. Một handler có thể là nơi **phát hiện** sự cố hoặc **khởi phát** một yêu cầu xử lý lỗi, không tự nhiên là một job scheduler bảo đảm delivery.

## 11. Exception chưa được xử lý và lỗi đã được catch

So sánh hai implementation:

~~~java
@Async
public void sendA(String id) {
    remoteService.send(id); // Ném IllegalStateException -> có thể đến handler
}

@Async
public void sendB(String id) {
    try {
        remoteService.send(id);
    } catch (IllegalStateException ex) {
        logger.warn("sendB failed");
        // Không rethrow -> handler không nhận exception này
    }
}
~~~

Đây là **đoạn minh họa tích hợp** với `remoteService`/`logger` và annotation được cấu hình. Nếu logic nghiệp vụ cố ý xử lý xong lỗi trong `catch`, handler không nên được gọi; nhưng nếu chỉ log rồi bỏ qua, hệ thống không còn tín hiệu failure tập trung.

Trường hợp công việc `@Async void` bên trong chỉ khởi chạy một `CompletableFuture` khác:

~~~java
@Async
public void detach(String id) {
    asyncClient.send(id);  // Trả CompletableFuture, nhưng bị bỏ qua
}
~~~

Nếu `asyncClient.send(id)` trả future chưa hoàn tất, phương thức `detach` có thể trở về bình thường trước khi future bên trong gặp lỗi. Lỗi của stage **sau khi method void đã kết thúc** không phải exception chưa bắt từ thân `detach`; `AsyncUncaughtExceptionHandler` không tự động theo dõi stage bị bỏ quên. Với thao tác cần hoàn tất end-to-end, hãy trả kết quả dưới dạng `CompletableFuture<Void>` và nối/quan sát stage đúng cách, hoặc thiết kế job status bền vững.

## 12. TaskRejectedException và overload cần được giám sát riêng

Một `ThreadPoolTaskExecutor` có giới hạn worker và queue có thể từ chối tác vụ khi quá tải. Từ chối xảy ra ở **lần nộp** nên đôi khi caller sẽ nhận `TaskRejectedException` trước cả khi worker bắt đầu chạy phương thức `@Async void`.

Snippet minh họa từ caller:

~~~java
try {
    notificationService.sendNotification(orderId);
} catch (TaskRejectedException rejected) {
    // Điều phối quá tải ở caller: phản hồi/backpressure hoặc lưu durable job.
}
~~~

Đây là **đoạn ghép vào ứng dụng**; `notificationService` là bean Spring proxy, `orderId` là input và `TaskRejectedException` thuộc `org.springframework.core.task`. `try/catch` này **có thể bắt lỗi submit**, nhưng **không bắt** `IllegalStateException` ném sau đó từ thân `@Async void` trong worker.

Đừng lập vòng `while(true)` gọi lại ngay khi reject: nó làm quá tải thêm nghiêm trọng. Thay vào đó, phân biệt request được phép từ chối với job bắt buộc lưu, có response `429`/`503` phù hợp, backoff/jitter và giới hạn retry, hoặc queue bền vững.

Một khác biệt khác: `CallerRunsPolicy` có thể thực thi task trên caller thread khi pool đang chạy và bão hòa. Nếu muốn giữ request latency có thể dự đoán, cần test policy này; không suy ra mọi lời gọi `@Async` luôn trả tức thì.

## 13. Ranh giới Spring proxy, context và transaction

**Proxy:** Với `@EnableAsync` ở chế độ proxy mặc định, gọi `this.sendNotification()` bên trong cùng bean thường bỏ qua interceptor. Handler cũng không can thiệp vào một lời gọi đồng bộ bỏ qua proxy như vậy. Kiểm thử cần gọi từ một bean/caller khác qua Spring-managed proxy.

**Phương thức không phù hợp:** Tránh phụ thuộc `@Async` trên private/final method trong class-based proxy vì không thể intercept theo cách thường mong đợi. Class/method phải được Spring proxy hợp lệ. Annotation không biến mọi lời gọi của một Java object tự tạo bằng `new` thành async.

**Thread context:** Worker không tự kế thừa an toàn toàn bộ `ThreadLocal`, MDC, security principal hoặc request attributes của caller. `params` trong handler không phải giải pháp context propagation chung. Truyền correlation ID an toàn qua command/context mechanism do ứng dụng thiết kế; sử dụng `TaskDecorator` hoặc adapter tương ứng khi cần.

**Transaction:** Transaction imperative thường gắn với thread. Lỗi trong worker không tự rollback transaction đã commit ở request thread; đồng thời handler được gọi **sau khi method lỗi** không tự mở một transaction mới để ghi trạng thái. Nếu muốn ghi failure status, cần transaction trong service xử lý hoặc `TransactionTemplate` có scope rõ.

**Bean singleton:** Nhiều task async có thể chạy đồng thời trên một service singleton. Handler cũng có thể bị gọi đồng thời; bộ đếm, cache, trạng thái dùng chung phải thread-safe. Nếu dùng logger và meter client sẵn có, xác minh tính thread-safe của các dependency.

## 14. Monitoring và test: đừng chỉ assert log

Một bộ test chuyên dụng cho `AsyncUncaughtExceptionHandler` nên xác minh:

1. **Lời gọi đi qua proxy:** tạo `ApplicationContext`, lấy bean từ Spring rồi gọi một method public `@Async void`.
2. **Exception của method:** method ném `IllegalStateException` với message đã biết; handler nhận đúng loại và message đó.
3. **Method metadata:** `method.getName()` đúng, `params.length` và dữ liệu đã được phép kiểm tra đúng; không dump raw token hoặc PII.
4. **Thực thi thread:** dùng `CountDownLatch` đợi handler, không test bằng `Thread.sleep` cố định hoặc giả định exception xảy ra trước lời gọi tiếp theo của caller.
5. **Phương thức void thành công:** handler không bị gọi khi task hoàn tất bình thường; cần latch/clock kiểm soát thời gian test.
6. **Exception đã được catch:** nếu method tự xử lý lỗi mà không rethrow, handler không được gọi.
7. **Future return:** một method `@Async CompletableFuture<Void>` lỗi thì returned future hoàn tất ngoại lệ; handler void không phải kênh lỗi của nó.
8. **Submit rejection:** tạo pool bounded và queue đầy với latch, assert caller nhận rejection theo policy; không chờ handler để phát hiện điều đó.
9. **Handler robustness:** giả lập logger/metric client lỗi; kiểm tra dự phòng và không gây retry hay gọi lại nghiệp vụ vô hạn.
10. **Idempotency / restart:** với job cần delivery, kiểm thử lost response, process restart, duplicate command và trạng thái job bền vững ở nơi lưu ngoài memory.

Ví dụ kiểm thử dùng `CountDownLatch` không nhằm biến mọi API thành blocking, mà để **test có điểm đồng bộ xác định**. Ví dụ trong mục 8 kiểm tra cả exception và method argument count, sau đó xác nhận caller không nhận task exception qua một `try/catch` bình thường.

Các metric hữu ích: `async_void_failure_total`, `async_submit_rejected_total`, queue depth, active worker, task duration, failure-by-method và tổng số job lỗi chưa xử lý. Không đưa object ID có cardinality lớn làm label metric; gắn vào log/tracing có kiểm soát nếu thực sự cần.

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Sửa thế nào |
| --- | --- | --- |
| “`try/catch` quanh `@Async void` sẽ bắt exception worker.” | Caller và worker khác đường thực thi | Dùng handler; chọn `CompletableFuture` nếu caller cần kết quả |
| “Chỉ cần khai báo bean `AsyncUncaughtExceptionHandler` là Spring sẽ luôn dùng.” | Handler cần được gắn vào async interceptor qua cấu hình | Dùng `AsyncConfigurer.getAsyncUncaughtExceptionHandler()` |
| “`@Async void` thất bại thì caller chắc chắn biết.” | Signature void không mang Future | Ghi metric/log/event; trả Future khi cần trạng thái |
| “Handler cũng nhận lỗi của `CompletableFuture`.” | Future đã có kênh lỗi riêng | `whenComplete`, `exceptionally`, `get()`/`join()` |
| “Handler sẽ nhận lỗi từ mọi `executor.execute`.” | API raw executor không nhất thiết qua `@Async` proxy | Thiết kế error handler riêng cho executor/task |
| “`TaskRejectedException` là một lỗi trong thân method.” | Nó có thể xảy ra ở bước nộp trước khi chạy | Bắt tại caller và quan sát metric reject |
| “Handler mặc định tự retry.” | `SimpleAsyncUncaughtExceptionHandler` chủ yếu logging | Retry có policy, job store, deadline và idempotency |
| “Log toàn bộ `params` là thuận tiện và vô hại.” | Có thể lộ bí mật/PII hoặc gây log bùng nổ | Sanitize, chỉ lưu method/type/correlation ID |
| “Handler luôn chạy trên thread riêng chuyên dụng.” | Nó thường được gọi trong đường thực thi task; policy executor có thể khác | Giữ handler ngắn, không blocking, test overload |
| “@Async void bảo đảm công việc sống qua JVM restart.” | Thread-pool task chỉ nằm trong memory | Dùng durable queue/job store nếu cần bảo đảm delivery |
| “Method tự catch/log rồi throw không liên quan.” | Nếu rethrow, handler vẫn có thể nhận exception | Phân định ownership logging để tránh log trùng và cảnh báo trùng |

## 16. Checklist khi đưa vào production

- `@EnableAsync` đã được bật trong đúng `ApplicationContext`, lời gọi qua Spring proxy.
- Method cần handler thực sự có kiểu trả về `void`, không phải `CompletableFuture<Void>`.
- Handler được cấu hình qua `AsyncConfigurer` và đã có integration test xác nhận chạy.
- Tôi biết exception nào bị bắt trong thân method và exception nào được rethrow đến handler.
- Handler ghi nhận lỗi an toàn, không dump nguyên `params` hoặc bí mật người dùng.
- Handler thread-safe, không block lâu, không làm thêm các thao tác không có hạn.
- Caller xử lý riêng `TaskRejectedException` tại thời điểm nộp.
- Tôi đã chọn có chủ đích giữa fire-and-forget `void` và API trả `CompletableFuture<Void>`.
- Tôi không dùng handler để retry reflection tức thời hoặc tạo thêm quá tải.
- Job quan trọng có idempotency key, durable state, retry policy, timeout và cơ chế reconciliation.
- Transaction, security context, logging context và lifecycle worker đều có owner rõ ràng.
- Metric/log/alert có thể phân biệt **task đã chạy rồi lỗi** với **task bị từ chối chưa chạy**.

**Kết luận:** `AsyncUncaughtExceptionHandler` là kênh xử lý exception **không được bắt từ phương thức `@Async` trả `void`** sau khi task thực sự chạy qua Spring interceptor. Nó có thông tin về lỗi, method và arguments, nhưng không chuyển lỗi trở lại caller, không làm tự động retry, và không thay thế `Future` hay job tracking. Với công việc cần kết quả/acknowledgement, ưu tiên API trả future hoặc cơ chế job bền vững; với fire-and-forget, phải có handler, logging, metric và chính sách xử lý failure rõ ràng.

## Tài liệu tham khảo chính thức

- Spring Framework — [AsyncUncaughtExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html): chữ ký `handleUncaughtException(Throwable, Method, Object...)`.
- Spring Framework — [SimpleAsyncUncaughtExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/SimpleAsyncUncaughtExceptionHandler.html): mặc định ghi log exception.
- Spring Framework — [AsyncConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html): cấu hình default executor và uncaught exception handler.
- Spring Framework — [@EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): kích hoạt async, proxy mode, default và handler configuration.
- Spring Framework — [@Async Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html): hỗ trợ return type `void`, `Future` và `CompletableFuture`.
- Spring Framework — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): exception management cho async methods và executor integration.
- Spring Framework — [TaskRejectedException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskRejectedException.html): xử lý từ chối lúc nộp task.
