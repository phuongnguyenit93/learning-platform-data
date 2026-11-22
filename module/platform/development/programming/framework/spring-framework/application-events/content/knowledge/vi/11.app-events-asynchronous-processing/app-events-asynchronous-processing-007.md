# AsyncUncaughtExceptionHandler trong Spring Framework Application Events

## 1. Vấn đề: listener bất đồng bộ lỗi thì ai nhận exception?

Spring cho phép một phương thức xử lý sự kiện chạy bất đồng bộ bằng cách kết hợp `@EventListener` và `@Async`. Với `@EnableAsync` được bật và phương thức được gọi qua cơ chế proxy của Spring, lời gọi phát sự kiện có thể kết thúc sau khi đã giao công việc cho executor, trong khi phương thức listener vẫn đang xử lý trên một luồng khác.

Giả sử listener dùng để gửi thông báo:

~~~java
@Async
@EventListener
public void notifyCustomer(OrderPlaced event) {
    throw new IllegalStateException("Dịch vụ thông báo tạm lỗi");
}
~~~

*Đây là đoạn minh họa trong một bean Spring; `OrderPlaced` là kiểu sự kiện do ứng dụng định nghĩa.*

Lúc này có hai điều quan trọng:

- Phương thức `notifyCustomer(...)` trả về `void`, vì thế bên phát không nhận được một `Future` để truy vấn kết quả hoặc exception.
- Exception phát sinh **trong luồng chạy bất đồng bộ** thông thường không được ném ngược về `ApplicationEventPublisher.publishEvent(...)`, vốn đã giao việc cho executor.

**`AsyncUncaughtExceptionHandler` là giao diện của Spring dùng để xử lý exception chưa được bắt từ phương thức `@Async` có kiểu trả về `void`.** Nó cho phép ứng dụng ghi log, bổ sung thông tin về method/tham số, gửi metric hoặc cảnh báo khi công việc chạy nền thất bại.

Tên “uncaught” có nghĩa là exception **không được chính phương thức bất đồng bộ bắt và xử lý**, chứ không phải mọi exception ở mọi nơi trong JVM đều chạy qua handler này.

~~~text
Publisher                       Executor / luồng chạy nền
    |                                        |
    | publishEvent(OrderPlaced)              |
    |       |                                |
    |       +--- @EventListener @Async ------> listener(event)
    |                                        |    |
    | publishEvent(...) trả về               |    X throw IllegalStateException
    |                                        |    |
    |                                        +--> AsyncUncaughtExceptionHandler
    |                                                |
    |                                                +--> ghi log / metric / cảnh báo
    |                                                     (không tự retry)
~~~

Trong ví dụ này, ứng dụng vẫn có thể tiếp tục xử lý yêu cầu ban đầu dù gửi thông báo thất bại. Chính vì vậy cần **quan sát và quyết định cách khắc phục lỗi** ở phía xử lý bất đồng bộ, thay vì coi việc publisher trả về bình thường là dấu hiệu toàn bộ listener đã thành công.

## 2. Hợp đồng của AsyncUncaughtExceptionHandler

Giao diện nằm trong gói `org.springframework.aop.interceptor`:

~~~java
public interface AsyncUncaughtExceptionHandler {
    void handleUncaughtException(
            Throwable ex,
            java.lang.reflect.Method method,
            Object... params);
}
~~~

Đây là **chữ ký API được rút gọn để giải thích**, không phải mã tự định nghĩa lại giao diện.

| Tham số | Ý nghĩa | Cách dùng hữu ích |
| --- | --- | --- |
| `Throwable ex` | Lỗi thoát khỏi phương thức `@Async` trả về `void`. | Xem loại exception, message, stack trace và nguyên nhân gốc. |
| `Method method` | Phương thức bất đồng bộ đã thất bại. | Ghi tên method hoặc vị trí xử lý để truy vết. |
| `Object... params` | Những đối số đã được truyền vào phương thức đó. | Tìm mã sự kiện, mã đơn hàng hoặc correlation ID khi phù hợp. |

Handler trả về `void`. Giá trị trả về của nó không thể trở thành kết quả của `publishEvent(...)` và không tạo cơ chế thông báo lỗi ngược cho bên phát.

Ví dụ handler riêng, dùng trong cấu hình Spring:

~~~java
public final class LoggingAsyncExceptionHandler
        implements AsyncUncaughtExceptionHandler {

    @Override
    public void handleUncaughtException(
            Throwable ex, Method method, Object... params) {
        System.err.println("Async failed in " + method.getName()
                + ": " + ex.getMessage());
    }
}
~~~

*Đoạn minh họa cần import `java.lang.reflect.Method` và `org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler`.*

Có thể triển khai bằng lớp riêng hoặc bằng lambda vì đây là giao diện hàm. Trong thực tế, nên dùng logger có stack trace, thông tin định danh tác vụ và metric; không ghi toàn bộ `params` nếu có mật khẩu, token hoặc dữ liệu cá nhân.

## 3. Khi nào handler được gọi, khi nào không?

Phân biệt theo nơi xử lý và **kiểu trả về của phương thức `@Async`**:

| Tình huống | Nơi nhận/quan sát lỗi |
| --- | --- |
| `@Async public void doWork(...)` ném exception chưa bắt | `AsyncUncaughtExceptionHandler` được cấu hình cho cơ chế `@Async`. |
| `@Async @EventListener public void onEvent(...)` ném exception chưa bắt | `AsyncUncaughtExceptionHandler` của cơ chế `@Async`. |
| Phương thức `@Async` trả `Future<T>` | `Future.get()` báo thất bại, thường dưới dạng `ExecutionException`. |
| Phương thức `@Async` trả `CompletableFuture<T>` | Future hoàn thành với trạng thái lỗi; có thể xử lý qua `whenComplete`, `handle`, `exceptionally` hoặc `join`. |
| Listener đồng bộ thông thường ném exception | Lỗi có thể truyền qua multicaster về `publishEvent(...)` nếu không bị bắt. |
| Lỗi bị bắt và xử lý hoàn toàn bên trong listener | Không còn exception chưa bắt để `AsyncUncaughtExceptionHandler` nhận. |
| Tác vụ bị executor từ chối ngay khi nộp | Đây là lỗi ở **bước giao việc**; có thể xuất hiện tại luồng gọi, không phải lỗi từ thân method đã chạy. |

Với mặc định của Spring `@Async`, exception từ phương thức `void` được ghi log bằng handler mặc định. **Handler mặc định không thay thế cơ chế lưu công việc hoặc tự động thử lại.**

Điều kiện cần nhớ: chỉ gắn `@Async` lên một phương thức chưa đủ nếu phương thức đó được tự gọi bằng `this.someMethod()` trong cùng bean; lời gọi tự đi qua đối tượng thay vì proxy có thể bỏ qua cơ chế bất đồng bộ trong chế độ proxy mặc định. `@EventListener` cần đặt trên bean do Spring quản lý và phải bật `@EnableAsync`.

## 4. Ví dụ đầy đủ Java 17+: listener lỗi và custom handler được gọi

Ví dụ dùng Spring Framework 6.2.9, Java 17+ và Maven. Chương trình tạo một `@Async @EventListener` cố ý ném `IllegalStateException`, cấu hình handler thông qua `AsyncConfigurer` và kiểm tra rằng publisher vẫn tiếp tục trong khi handler xử lý lỗi ở luồng khác.

Cấu trúc:

~~~text
async-exception-demo/
├── pom.xml
└── src/main/java/AsyncUncaughtExceptionDemo.java
~~~

Nội dung `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-exception-demo</artifactId>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Nội dung `src/main/java/AsyncUncaughtExceptionDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncUncaughtExceptionDemo {

    private static final CountDownLatch RELEASE = new CountDownLatch(1);
    private static final CountDownLatch HANDLED = new CountDownLatch(1);

    public record OrderPlaced(String orderId) {}

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                     new AnnotationConfigApplicationContext(DemoConfig.class)) {

            System.out.println("Publisher: trước publishEvent");
            context.publishEvent(new OrderPlaced("OD-7"));
            System.out.println("Publisher: sau publishEvent");

            // Chỉ để bảo đảm thứ tự minh họa trên stdout.
            RELEASE.countDown();

            if (!HANDLED.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Handler không chạy kịp");
            }
            System.out.println("Publisher: handler đã chạy");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class DemoConfig implements AsyncConfigurer {

        @Bean
        public OrderListener orderListener() {
            return new OrderListener();
        }

        @Bean(name = "taskExecutor")
        public ThreadPoolTaskExecutor taskExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-");
            return executor; // Spring khởi tạo và đóng executor như một bean.
        }

        @Override
        public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
            return (ex, method, params) -> {
                OrderPlaced event = (OrderPlaced) params[0];
                System.out.println("Handler: " + method.getName()
                        + "(" + event.orderId() + "): " + ex.getMessage());
                HANDLED.countDown();
            };
        }
    }

    public static class OrderListener {

        @Async
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            try {
                RELEASE.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Luồng đã bị ngắt", ex);
            }

            System.out.println("Listener: nhận " + event.orderId());
            throw new IllegalStateException(
                    "xử lý thất bại " + event.orderId());
        }
    }
}
~~~

Từ thư mục có `pom.xml`, chạy bằng Java 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=AsyncUncaughtExceptionDemo
~~~

Các dòng do chính chương trình in ra stdout, không tính log từ Maven hoặc framework:

~~~text
Publisher: trước publishEvent
Publisher: sau publishEvent
Listener: nhận OD-7
Handler: onOrderPlaced(OD-7): xử lý thất bại OD-7
Publisher: handler đã chạy
~~~

### Giải thích kết quả

1. `@EnableAsync` bật hạ tầng xử lý `@Async`. Bean `taskExecutor` là executor mà hạ tầng `@Async` tìm thấy theo tên quy ước; luồng chạy tác vụ có tiền tố `event-`.
2. `@EventListener` đăng ký phương thức `onOrderPlaced` để nhận `OrderPlaced`. Đối tượng `OrderPlaced` không phải kế thừa `ApplicationEvent`; Spring hỗ trợ sự kiện dạng payload.
3. Khi publisher gọi `publishEvent(...)`, Spring chuyển việc thực thi phương thức `@Async` cho executor. Vì vậy publisher có thể in “sau publishEvent” mà không phải đợi thân listener xử lý xong.
4. `RELEASE` là chốt đồng bộ **chỉ dành cho ví dụ**: nó buộc listener chờ đến khi publisher in xong dòng thứ hai. Nhờ đó thứ tự stdout được xác định rõ mà không phụ thuộc vào tốc độ lập lịch của hệ điều hành.
5. Listener in dòng nhận sự kiện, sau đó ném `IllegalStateException`. Phương thức trả `void` nên lỗi được đưa tới `getAsyncUncaughtExceptionHandler()`, cùng `Method` và những tham số thực sự đã truyền cho method.
6. Handler in lỗi và gọi `HANDLED.countDown()`. `main` đợi tín hiệu đó để chương trình kết thúc sau khi handler hoàn tất.

Trong code sản xuất, **không dùng chốt `RELEASE` để buộc tác vụ bất đồng bộ đợi publisher**. Chốt này chỉ làm kết quả ví dụ trở nên xác định, tránh hiểu sai rằng bất đồng bộ luôn hoàn tất theo thứ tự như stdout.

## 5. Cấu hình handler thực tế với AsyncConfigurer

Một cách rõ ràng để cung cấp handler chung cho các method `@Async` do Spring quản lý là triển khai `AsyncConfigurer` trong lớp `@Configuration`:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (ex, method, params) -> {
            // Ghi log kèm stack trace, tên phương thức và mã tác vụ.
            // Phát metric hoặc tạo cảnh báo theo nhu cầu.
        };
    }
}
~~~

*Đây là đoạn cấu hình độc lập về mặt ý tưởng; cần các import Spring phù hợp. Đoạn này chưa thể chạy thành một chương trình hoàn chỉnh nếu không đặt trong ứng dụng Spring.*

`getAsyncUncaughtExceptionHandler()` cấu hình đường xử lý exception của `@Async`. Để điều chỉnh executor, có thể cấu hình thêm `getAsyncExecutor()` trên `AsyncConfigurer` hoặc khai báo executor bean theo tên/qualifier Spring hỗ trợ.

Khi cần các nhóm công việc có quy tắc lỗi khác nhau, có thể đặt `try/catch` ngay trong listener và gọi một dịch vụ chuyên xử lý lỗi, hoặc tổ chức executor và service riêng. Một `AsyncUncaughtExceptionHandler` chung thường phù hợp cho lỗi bất ngờ cần log, metric và cảnh báo, nhưng không thay thế logic bù trừ nghiệp vụ.

## 6. AsyncUncaughtExceptionHandler khác ErrorHandler của event multicaster

Spring có **hai điểm mở rộng khác nhau**, dễ bị nhầm vì đều “xử lý lỗi sự kiện”:

| Tiêu chí | `AsyncUncaughtExceptionHandler` | `SimpleApplicationEventMulticaster.setErrorHandler(...)` |
| --- | --- | --- |
| Nằm trong cơ chế | Hạ tầng gọi method `@Async` của Spring. | Hạ tầng multicaster gọi `ApplicationListener`. |
| Dùng điển hình | Exception từ `@Async` trả về `void`, kể cả `@Async @EventListener`. | Exception phát sinh trực tiếp trong lần multicaster gọi listener. |
| Cách cấu hình | `AsyncConfigurer`, hoặc cấu hình `@Async` tương đương. | Bean `applicationEventMulticaster` cấu hình `setErrorHandler`. |
| Tham số nhận | `Throwable`, `Method` và đối số phương thức. | `Throwable` của lần gọi listener. |
| Tác động lên publisher | Exception xảy ra sau khi tác vụ được giao không tự truyền về publisher. | Với listener đồng bộ, handler có thể hấp thụ hoặc ném lại lỗi, từ đó ảnh hưởng đến lời gọi phát sự kiện. |

**Ví dụ quan trọng:** Multicaster mặc định gọi một adapter của `@EventListener` đồng bộ, nhưng phương thức đích có `@Async`. Adapter/proxy nộp công việc và trả về trước khi thân phương thức chạy. Nếu thân phương thức sau đó ném lỗi, `AsyncUncaughtExceptionHandler` xử lý lỗi; `ErrorHandler` của multicaster thường không nhìn thấy exception đó.

Nếu thay chính multicaster bằng `SimpleApplicationEventMulticaster` có `setTaskExecutor(...)`, việc gọi listener chuyển sang luồng khác theo cơ chế của multicaster, và `setErrorHandler(...)` là điểm xử lý lỗi của lần gọi listener đó. Không nên mặc định hai kiểu cấu hình sẽ kích hoạt cùng một handler hoặc cùng một đường truyền exception.

## 7. Phân biệt với exception của Future và CompletableFuture

`@Async` không buộc mọi method trả `void`. Một method dịch vụ có thể trả `Future<T>` hoặc `CompletableFuture<T>` để bên gọi biết tác vụ thành công hay thất bại.

Ví dụ minh họa trong bean dịch vụ Spring:

~~~java
@Async
public java.util.concurrent.CompletableFuture<String> rebuildIndex(String id) {
    if (id.isBlank()) {
        throw new IllegalArgumentException("Mã rỗng");
    }
    return java.util.concurrent.CompletableFuture.completedFuture(
            "indexed:" + id);
}
~~~

*Đây là phương thức minh họa, không phải chương trình tự chạy.*

Khi `id` rỗng, kết quả bất đồng bộ hoàn thành với exception. Bên nhận `CompletableFuture` có thể xử lý như sau:

~~~java
future.whenComplete((value, error) -> {
    if (error != null) {
        // Ghi nhận thất bại hoặc thực hiện chính sách phục hồi.
    }
});
~~~

`AsyncUncaughtExceptionHandler` **không phải** nơi chính để xử lý exception của method `@Async` trả `Future` hay `CompletableFuture`; lỗi được phản ánh trong kết quả Future. `get()` thường ném `ExecutionException` chứa nguyên nhân, còn `join()` ném `CompletionException`.

Trong mô hình Spring Application Events, `publishEvent(...)` không trả một `CompletableFuture` tổng hợp cho các `@EventListener`. Vì vậy không thể giả định publisher có thể `join()` để biết toàn bộ listener đã hoàn tất. Nếu nghiệp vụ cần kết quả, cân nhắc gọi trực tiếp một service trả Future hoặc thiết kế cơ chế theo dõi tác vụ riêng.

## 8. Ảnh hưởng đến giao dịch, dữ liệu và độ tin cậy

Vì listener `@Async` xử lý trên luồng khác:

- Exception trong listener bất đồng bộ thường **không làm phương thức publisher tự thất bại** sau khi đã giao tác vụ thành công.
- Giao dịch `@Transactional` và ngữ cảnh `ThreadLocal` ở luồng publisher **không được tự động mang sang** luồng listener. Listener có thể đọc dữ liệu khi giao dịch bên phát chưa commit, tùy thời điểm và mức cô lập.
- Handler được gọi khi lỗi xảy ra, nhưng **không tự rollback giao dịch của publisher** và không khôi phục những tác dụng phụ đã phát sinh.
- Handler không tự cung cấp retry, lưu thông điệp bền vững hoặc chuyển sự kiện sang máy chủ khác; nếu JVM dừng hoặc executor mất việc, event nội bộ không có cơ chế phát lại mặc định.
- `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` có thể hữu ích nếu chỉ muốn thực hiện xử lý sau khi giao dịch thành công; khi kết hợp với `@Async`, vẫn phải thiết kế riêng cách giám sát lỗi và bảo đảm xử lý.

Đối với tác vụ phụ như thống kê, ghi log hoặc gửi thông báo không bắt buộc, handler có thể ghi log và cảnh báo. Với công việc bắt buộc như tính phí, trừ tồn kho hoặc đồng bộ giữa hệ thống, cần cân nhắc lời gọi trực tiếp, retry có giới hạn, hàng đợi bền vững hoặc transactional outbox để không âm thầm mất công việc.

## 9. Nguyên tắc triển khai và quan sát lỗi

1. **Ghi lại nguyên nhân gốc.** Ghi exception cùng stack trace và tên method. Chỉ in `ex.getMessage()` như ví dụ là chưa đủ cho vận hành thực tế.
2. **Gắn mã tương quan.** Dùng mã sự kiện/đơn hàng hoặc correlation ID từ `params`. Tránh ghi toàn bộ payload nếu chứa thông tin nhạy cảm.
3. **Đếm và cảnh báo.** Có thể tăng metric cho số lần thất bại theo tên listener và loại lỗi, đồng thời đặt ngưỡng cảnh báo.
4. **Phân biệt lỗi nghiệp vụ và lỗi hệ thống.** Ví dụ dữ liệu không hợp lệ có thể cần ghi nhận để xử lý thủ công; timeout tạm thời có thể phù hợp với retry có backoff.
5. **Không thử lại vô hạn ngay trong handler.** Handler không biết sẵn tác vụ nào an toàn để thực thi lại; retry phải xét tính lặp an toàn (idempotency), số lần thử và trạng thái dữ liệu.
6. **Giám sát executor.** Hàng đợi đầy hoặc bị từ chối tác vụ xảy ra trước khi listener chạy, nên cũng phải theo dõi chỉ số executor và lỗi nộp tác vụ.
7. **Kiểm tra cơ chế proxy.** `@EnableAsync` phải được bật; listener là bean Spring; method cần có thể được proxy; lời gọi nội bộ qua `this` không kích hoạt `@Async` trong chế độ proxy thông thường.

Không nên dựa vào log mặc định như một cơ chế phục hồi. Một exception có thể đã được ghi nhận nhưng tác vụ vẫn thất bại và không được chạy lại.

## 10. Câu hỏi tự kiểm tra

**1.** Một listener `@Async @EventListener` trả `void` ném `IllegalStateException` sau khi publisher đã gọi `publishEvent(...)`. Publisher có nhận trực tiếp exception đó không?

**Đáp án:** Thông thường không. Exception phát sinh trong luồng tác vụ của `@Async`; `AsyncUncaughtExceptionHandler` là điểm xử lý được thiết kế cho trường hợp method `void`.

**2.** Nếu listener bắt được exception bằng `try/catch` và xử lý hoàn toàn, handler có nhận lỗi đó không?

**Đáp án:** Không. Không còn lỗi chưa bắt thoát khỏi method để chuyển đến handler.

**3.** Nếu `@Async` trả `CompletableFuture<String>`, phải lấy exception từ đâu?

**Đáp án:** Từ kết quả Future bằng `get()`, `join()` hoặc các callback như `whenComplete(...)`. `AsyncUncaughtExceptionHandler` không xử lý Future như trường hợp method `void`.

**4.** Cấu hình `SimpleApplicationEventMulticaster.setErrorHandler(...)` có tương đương cấu hình `AsyncConfigurer.getAsyncUncaughtExceptionHandler()` không?

**Đáp án:** Không. Hai handler nằm ở hai tầng khác nhau: một tầng gọi listener của multicaster, một tầng thực thi phương thức `@Async`.

**5.** Handler nhận được exception có nghĩa là sự kiện đã được thử lại hoặc giao dịch publisher bị rollback không?

**Đáp án:** Không. Handler chỉ là điểm xử lý ngoại lệ; retry, bù trừ giao dịch và bảo đảm giao nhận cần được thiết kế riêng.

## Tài liệu tham khảo

- [Spring Framework Reference — Exception Management with @Async](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): cách `@Async` xử lý exception cho `void` và `Future`.
- [Spring Framework Reference — Asynchronous Event Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): giới hạn của `@Async @EventListener` và quan hệ với `publishEvent(...)`.
- [Javadoc — AsyncUncaughtExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/interceptor/AsyncUncaughtExceptionHandler.html): hợp đồng `handleUncaughtException(Throwable, Method, Object...)`.
- [Javadoc — AsyncConfigurer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html): cấu hình executor và handler cho `@Async`.
