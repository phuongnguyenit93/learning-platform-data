# Async listener trả về Future trong Spring Application Events

## 1. Mục tiêu và bối cảnh

Trong Spring Framework, một phương thức xử lý sự kiện có thể dùng `@EventListener` để nhận event, và dùng `@Async` để chạy công việc trên executor. Vì Java có `Future<T>` và `CompletableFuture<T>`, câu hỏi tự nhiên là: **nếu async listener trả về Future, bên gọi `publishEvent(...)` có nhận được Future để đợi kết quả hay không?**

**Không.** `ApplicationEventPublisher.publishEvent(...)` có kiểu trả về `void`. Event publisher không có API trả lại danh sách `Future` của các listener. Dù phương thức listener có kiểu trả về `Future<T>` hay `CompletableFuture<T>`, giá trị đó không tự chuyển thành kết quả của lệnh `publishEvent`.

Tuy nhiên, `@Async` **có hỗ trợ phương thức trả về `Future` hoặc `CompletableFuture`**, khi phương thức ấy được gọi trực tiếp qua Spring proxy. Vì vậy cần phân biệt ba vai trò:

1. **Event publisher:** phát sự kiện qua `ApplicationEventPublisher`, không nhận Future từ lời gọi này.
2. **Event listener:** phản ứng với sự kiện; khi được đánh dấu `@Async`, phần thân xử lý chạy ở luồng khác. Phương thức listener có thể khai báo `CompletableFuture<Void>`, nhưng publisher không trực tiếp lấy được handle ấy.
3. **Async service:** bean có phương thức `@Async` được caller gọi trực tiếp; caller nhận `Future<T>` từ proxy để theo dõi giá trị, lỗi hoặc thời điểm hoàn tất.

Bài học tập trung vào semantics của `Future` trong **Spring Application Events**, cách nhận kết quả an toàn và các giới hạn quan trọng của async listener.

## 2. `Future` và `CompletableFuture` có ý nghĩa gì?

`Future<T>` trong `java.util.concurrent` đại diện cho kết quả có thể có trong tương lai.

- `isDone()`: cho biết tác vụ đã hoàn tất theo hợp đồng Future (bao gồm cả hủy hay lỗi); không chứng minh tác vụ thành công.
- `get()`: chờ đến khi có kết quả, có thể chặn thread vô hạn nếu công việc không kết thúc.
- `get(timeout, unit)`: chờ có giới hạn; có thể ném `TimeoutException`, `ExecutionException` hoặc `InterruptedException`.
- `cancel(...)`: yêu cầu hủy theo khả năng của triển khai; không bảo đảm đã hoàn tác tác dụng phụ như ghi database hay gọi API ngoài.

`CompletableFuture<T>` triển khai `Future<T>` đồng thời hỗ trợ `CompletionStage<T>`. Nó cung cấp `thenApply`, `thenCompose`, `thenAccept`, `whenComplete`, `exceptionally` và `handle` để ghép bước xử lý, phản hồi kết quả và lỗi mà không buộc caller chặn thread ngay lập tức.

Trong Spring, `@Async` cho phép phương thức có kiểu trả về `void`, `Future<T>` hoặc `CompletableFuture<T>`. Không thể tùy ý khai báo `String` rồi kỳ vọng `@Async` tự bọc thành Future. Đặc biệt, mã **bên trong phương thức đích** thường trả về một Future đã hoàn tất, ví dụ `CompletableFuture.completedFuture(value)`; khi caller gọi **qua proxy**, Spring cung cấp Future đại diện cho toàn bộ công việc được thực thi trên executor.

~~~java
// Đoạn minh họa: phương thức thuộc Spring bean, được gọi qua Spring proxy.
@Async("lessonExecutor")
public CompletableFuture<String> calculate(String id) {
    String result = "done:" + id;
    return CompletableFuture.completedFuture(result);
}
~~~

`completedFuture` trong thân hàm không có nghĩa caller chạy đồng bộ: phần thân vẫn thực thi trên executor nếu lời gọi đi qua proxy `@Async`.

## 3. Kết hợp `@EventListener` và `@Async`: ai nhận Future?

Xét listener khai báo:

~~~java
// Đoạn minh họa, chưa phải ứng dụng độc lập.
@Async("lessonExecutor")
@EventListener
public CompletableFuture<Void> onOrderPlaced(OrderPlaced event) {
    process(event);
    return CompletableFuture.completedFuture(null);
}
~~~

Về mặt khai báo, kiểu `CompletableFuture<Void>` phù hợp với `@Async`. Khi Spring gọi phương thức qua proxy, phần thân chạy bất đồng bộ. Nhưng điểm mấu chốt là **đầu vào của publisher vẫn là `publishEvent(event)` với kiểu trả về `void`**, ví dụ:

~~~java
publisher.publishEvent(new OrderPlaced("A-1"));
// Lệnh này không sinh ra Future cho publisher.
~~~

Không thể viết:

~~~java
// SAI: không biên dịch, vì publishEvent trả về void.
CompletableFuture<Void> future = publisher.publishEvent(new OrderPlaced("A-1"));
~~~

`@EventListener` còn có một quy tắc riêng: giá trị trả về khác `void` của **listener đồng bộ** có thể được Spring sử dụng để phát event tiếp theo. Tài liệu Spring lưu ý không dựa vào việc trả về giá trị của **asynchronous listener** để phát event tiếp theo; nếu cần, inject `ApplicationEventPublisher` và chủ động gọi `publishEvent(new FollowUpEvent(...))`. Không xem `Future<T>` từ listener là giao thức request/response ngầm giữa publisher và listener.

**Chọn cách làm theo mục đích:**

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Fire-and-forget, listener ghi log/gửi notification độc lập | `@Async @EventListener void handle(Event e)` cùng cơ chế log, retry, giám sát |
| Bên gọi muốn lấy một kết quả async một cách rõ ràng | Gọi trực tiếp một `@Async` service trả về `CompletableFuture<T>` |
| Vẫn muốn dùng event nhưng caller cần một kết quả nội bộ | Thiết kế kênh phản hồi tường minh (ví dụ `CompletableFuture<T>` gắn vào event hoặc map theo correlation ID); chỉ phù hợp khi các thành phần cùng process và có quy ước hoàn thành/lỗi |
| Công việc có thứ tự, retry và độ bền xuyên tiến trình | Workflow/service điều phối, hàng đợi bền vững hoặc broker với cơ chế correlation và acknowledgment |

## 4. Ví dụ hoàn chỉnh Java 17+: Future của listener và Future của service

Ví dụ sau dùng Spring Framework 6.2.12, Java 17+ và Maven. Có hai đường đi:

- **Event:** publisher tạo `CompletableFuture<String> reply` rồi đính kèm nó vào một `WorkRequested` event. Listener `@Async` trả về `CompletableFuture<Void>` theo chữ ký phương thức và hoàn thành `reply` của event bằng kết quả nghiệp vụ. Đây là một **kênh phản hồi do ứng dụng tự định nghĩa**, không phải Future do `publishEvent` trả về.
- **Gọi bean trực tiếp:** caller lấy bean `AsyncService` từ Spring context, gọi phương thức `@Async` và **nhận trực tiếp** `CompletableFuture<String>` qua proxy.

Tạo cấu trúc:

~~~text
async-listener-future/
├── pom.xml
└── src/main/java/demo/AsyncFutureEventsDemo.java
~~~

### `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>async-listener-future</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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

### `src/main/java/demo/AsyncFutureEventsDemo.java`

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncFutureEventsDemo {

    // Event mang một reply handle rõ ràng, dành cho ví dụ nội bộ cùng process.
    public record WorkRequested(
            String jobId,
            CompletableFuture<String> reply) {
    }

    @Configuration
    @EnableAsync
    public static class Config {

        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("lesson-");
            return executor;
        }

        @Bean
        public AsyncEventListener asyncEventListener() {
            return new AsyncEventListener();
        }

        @Bean
        public AsyncService asyncService() {
            return new AsyncService();
        }
    }

    public static class AsyncEventListener {

        @Async("lessonExecutor")
        @EventListener
        public CompletableFuture<Void> onWorkRequested(WorkRequested event) {
            try {
                if (event.jobId().isBlank()) {
                    throw new IllegalArgumentException("jobId is blank");
                }

                String result = "event:" + event.jobId();
                // Quan trọng: hoàn tất Future do ứng dụng đặt trong event.
                event.reply().complete(result);

                // Future trả về từ listener không được publishEvent trao cho caller.
                return CompletableFuture.completedFuture(null);
            } catch (RuntimeException failure) {
                // Nếu tác vụ thất bại, caller đợi reply cũng nhìn thấy lỗi.
                event.reply().completeExceptionally(failure);
                throw failure;
            }
        }
    }

    public static class AsyncService {

        @Async("lessonExecutor")
        public CompletableFuture<String> execute(String id) {
            // Giá trị tạm bên trong target method được proxy xử lý.
            return CompletableFuture.completedFuture("service:" + id);
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {

            // Cách 1: phát event, nhận phản hồi qua handle gắn vào event.
            CompletableFuture<String> reply = new CompletableFuture<>();
            context.publishEvent(new WorkRequested("A-1", reply));
            String eventResult = reply.get(5, TimeUnit.SECONDS);
            System.out.println("Event reply: " + eventResult);

            // Cách 2: gọi @Async service qua Spring proxy và nhận Future.
            CompletableFuture<String> directFuture =
                    context.getBean(AsyncService.class).execute("B-2");
            String serviceResult = directFuture.get(5, TimeUnit.SECONDS);
            System.out.println("Direct Future: " + serviceResult);
        }
    }
}
~~~

Chạy ở thư mục `async-listener-future` (cần JDK 17+ và Maven):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.AsyncFutureEventsDemo
~~~

Hai dòng do chương trình in ra (`stdout`) theo thứ tự:

~~~text
Event reply: event:A-1
Direct Future: service:B-2
~~~

**Vì sao ví dụ có thứ tự output xác định?** Trong `main`, lệnh `reply.get(5, SECONDS)` chờ listener hoàn thành phản hồi trước khi in dòng thứ nhất. Sau đó main mới gọi async service, chờ `directFuture.get(...)` rồi in dòng thứ hai. Điều này chỉ kiểm soát hai thao tác trong ví dụ, không có nghĩa các listener bất đồng bộ khác trong ứng dụng sẽ luôn chạy đúng thứ tự phát sự kiện.

**Ý nghĩa của hai Future:**

- `onWorkRequested` có chữ ký trả `CompletableFuture<Void>`, đáp ứng kiểu trả về được `@Async` hỗ trợ. Tuy nhiên publisher **không cầm được** Future do Spring xử lý khi gọi listener.
- `reply` là Future do **ứng dụng tạo trước khi publish**. Listener hoàn thành nó; publisher có thể tự chờ hoặc đăng ký callback. Đây là quy ước bổ sung của ứng dụng, đòi hỏi định nghĩa cách hoàn thành exceptional, timeout và trách nhiệm phản hồi.
- `directFuture` là Future mà caller **nhận được từ lời gọi đến `AsyncService` qua Spring proxy**. Đây là đường đi điển hình khi kết quả async là yêu cầu trực tiếp của caller.

Trong code, `reply` được hoàn thành trước khi listener return; điều đó là một lựa chọn cụ thể của ví dụ. Nếu logic có nhiều bước, chỉ `complete` sau khi các hiệu ứng cần thiết đã hoàn tất và dữ liệu nhất quán.

## 5. Khi nào nên khai báo `Future<T>` ngay trên listener?

Về kiểu trả về của `@Async`, `Future<T>` và `CompletableFuture<T>` hợp lệ. Với listener, điều cần xem xét là **bên nào sử dụng kết quả**.

**Trường hợp chỉ làm side effect** như gửi email, ghi audit hoặc cập nhật cache: listener `void` thường dễ hiểu hơn, vì không có caller dùng giá trị trả về. Khi đó cần chính sách báo lỗi/giám sát riêng.

~~~java
// Minh họa trên Spring bean có @EnableAsync và executor hợp lệ.
@Async("lessonExecutor")
@EventListener
public void sendNotification(OrderPlaced event) {
    notificationService.send(event.orderId());
}
~~~

**Trường hợp listener khai báo Future:** `CompletableFuture<Void>` thể hiện hợp đồng của `@Async` ở cấp phương thức mà không hứa một giá trị phản hồi nghiệp vụ. Việc khai báo `CompletableFuture<Result>` với ý định publisher tự nhận `Result` là dễ gây nhầm lẫn; bản thân `publishEvent` không cho caller handle đó. Hơn nữa, cơ chế xử lý giá trị trả về của `@EventListener` có ý nghĩa riêng liên quan tới event tiếp theo, nên không dùng return value để dựng một giao thức trả lời không được tài liệu bảo đảm.

**Trường hợp bắt buộc trả giá trị cho caller:** ưu tiên một **async service** trả `CompletableFuture<Result>` được gọi trực tiếp; hoặc nếu có lý do kiến trúc phải giữ event, hãy dùng một kênh phản hồi được thiết kế rõ ràng như ví dụ trên. Future gắn vào event chỉ hoạt động trong cùng JVM; nó không phải thông điệp bền vững và không truyền nguyên trạng qua Kafka/RabbitMQ hoặc giữa hai service.

## 6. Xử lý lỗi, timeout và completion đúng cách

### 6.1. `get` khác `join`

- `future.get(timeout, TimeUnit.SECONDS)`: chặn thread có giới hạn; lỗi thường được bọc trong `ExecutionException`.
- `future.join()`: chặn khi cần, không có đối số timeout; lỗi được bọc trong `CompletionException`. Tránh dùng `join()` vô hạn trong request thread nếu listener có thể treo.
- `future.whenComplete((value, error) -> ...)`: đăng ký callback để quan sát cả thành công lẫn thất bại. Cần tránh ném ngoại lệ trong callback mà không có handler tiếp theo.
- `future.exceptionally(error -> fallback)`: tạo giá trị thay thế hoặc xử lý lỗi; không được âm thầm biến lỗi nghiệp vụ quan trọng thành thành công giả.
- `future.thenCompose(nextAsyncStep)`: ghép các bước bất đồng bộ có phụ thuộc dữ liệu mà không cần chặn giữa các bước.

Ví dụ sử dụng phản hồi mà không chặn publisher:

~~~java
// Minh họa: reply đã được đặt trong event.
reply.orTimeout(5, TimeUnit.SECONDS)
     .whenComplete((value, failure) -> {
         if (failure != null) {
             logFailure(failure);
         } else {
             consume(value);
         }
     });
~~~

Đoạn trên dùng `logFailure` và `consume` như tên hàm nghiệp vụ minh họa; phải định nghĩa hai hàm đó trong ứng dụng. `orTimeout` (Java 9+) hoàn tất Future theo nhánh lỗi khi hết hạn **nhưng không tự dừng công việc đã gửi sang executor**. Nếu listener đến muộn, thao tác `complete` có thể trả `false` vì Future đã được kết thúc trước đó.

### 6.2. Nếu không có listener hoặc executor từ chối task?

Không có người hoàn tất `reply` thì Future có thể chờ mãi. Tương tự, nếu executor bị shutdown, pool đầy hoặc reject task, công việc có thể chưa vào hàng đợi; cần xử lý lỗi tại ranh giới phát event, timeout và có đường fallback. Không được coi `publishEvent` trả về là bằng chứng tất cả listener đã chạy thành công.

Nếu dùng map kiểu `Map<CorrelationId, CompletableFuture<Result>>` cho nhiều request, phải xóa entry ở cả nhánh success, failure và timeout để tránh rò rỉ bộ nhớ; cân nhắc dùng ID duy nhất cho mỗi request và chỉ có một nguồn chịu trách nhiệm hoàn thành phản hồi.

### 6.3. Exception thuộc về ai?

Với phương thức `@Async` trả `Future<T>` được gọi trực tiếp, caller có thể quan sát thất bại qua Future. Với async listener được gọi bởi hệ thống event, publisher không có Future đó để `get()`; lỗi không tự ném ngược về thread gọi `publishEvent`. Đối với `@Async void`, Spring có `AsyncUncaughtExceptionHandler` để xử lý exception không bắt được. Trong mọi trường hợp, phải có log, metrics, correlation ID và chính sách retry phù hợp.

Trong ví dụ, listener chủ động gọi `event.reply().completeExceptionally(failure)` trước khi ném lỗi. Vì vậy bên chờ `reply.get(...)` nhận `ExecutionException` chứa nguyên nhân. Nếu thiếu bước này, reply có thể không bao giờ hoàn tất dù listener đã lỗi.

## 7. Những giới hạn khác của async listener

### 7.1. Spring proxy và `@EnableAsync`

`@EnableAsync` bật việc nhận diện `@Async`; listener và service phải là **bean do Spring quản lý**, phương thức có thể được proxy intercept. Một lời gọi `this.asyncMethod()` trong cùng object (self-invocation) thường bỏ qua proxy ở proxy mode, dẫn tới chạy đồng bộ ngoài dự kiến. Không đặt `@Async` trực tiếp trên phương thức bên trong `@Configuration`. Chọn và đặt tên executor rõ ràng; bảo đảm pool đủ tài nguyên, có queue và phương án rejection phù hợp.

### 7.2. Transaction và thread context

Công việc trên thread khác không tự kế thừa Spring transaction của publisher, request-bound `ThreadLocal`, MDC hay security context nếu chưa có cơ chế truyền context. Nếu listener phải chạy sau khi giao dịch commit, cân nhắc `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` với hiểu biết đúng về transaction lifecycle; annotation này **không tự biến Future của listener thành phản hồi của publisher**. Nếu cần bảo toàn dữ liệu qua crash giữa commit và xử lý async, cân nhắc transactional outbox hoặc hàng đợi bền vững.

### 7.3. Thứ tự, nhiều listener và độ tin cậy

Nếu nhiều listener cùng nhận event, từng listener có thể hoàn tất ở thời điểm khác nhau; `@Order` không phải cơ chế bảo đảm thứ tự hoàn tất của các tác vụ async. Một Future phản hồi duy nhất không tự giải quyết trường hợp nhiều listener cần hội tụ kết quả: phải định nghĩa ai là owner của reply hoặc dùng `CompletableFuture.allOf` trên các Future **caller thật sự nắm giữ**. Không được suy đoán rằng một phản hồi thành công đồng nghĩa toàn bộ side effect của mọi listener đã thành công.

Nếu cần kết quả chắc chắn, retry, audit và xử lý trên nhiều tiến trình, giải pháp event thuần in-memory với một Future không đủ. Lúc này nên nâng mô hình lên job có ID, trạng thái lưu bền vững và API truy vấn hoặc broker/workflow tương ứng.

## 8. Những lỗi phổ biến

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Gán kết quả `publishEvent` vào `Future` | Phương thức trả `void` | Gọi trực tiếp async service hoặc tạo kênh reply rõ ràng |
| Dùng `@Async public String handle(...)` | Kiểu trả về không hợp đồng `@Async` | Dùng `void`, `Future<T>`, `CompletableFuture<T>` |
| Trả `CompletableFuture<String>` từ listener rồi kỳ vọng publisher nhận giá trị | Event dispatch không phải request/response | Dùng Future phản hồi riêng hoặc service có API tường minh |
| Gọi `future.get()` không timeout ở request thread | Có thể treo khi listener lỗi/hung/rejection | Đặt timeout và xử lý error/retry |
| Không `completeExceptionally` khi xử lý lỗi | Bên chờ phản hồi có thể timeout dù listener đã thất bại | Hoàn tất reply ở cả hai nhánh |
| Gọi `@Async` qua `this` | Có thể bỏ qua Spring proxy | Gọi qua bean/proxy khác |
| Tưởng `@Order` bảo đảm async listener hoàn tất theo thứ tự | Executor nhiều thread chạy song song | Điều phối hoặc serialize workflow khi bắt buộc |
| Mang `CompletableFuture` trong event qua broker | Future là handle trong bộ nhớ process | Dùng correlation ID và trạng thái/kênh reply phân tán |

## 9. Checklist áp dụng vào thực tế

1. Xác định người cần **kết quả**: publisher, một service gọi trực tiếp hay một downstream consumer.
2. Nếu publisher chỉ cần thông báo sự kiện, dùng listener bất đồng bộ độc lập và theo dõi lỗi ngoài luồng.
3. Nếu publisher cần chờ và đọc kết quả, ưu tiên `@Async` service trả `CompletableFuture<T>`; nếu vẫn dùng event, định nghĩa rõ kênh reply.
4. Với kênh reply, quy định timeout, complete/completeExceptionally, request ID, số listener chịu trách nhiệm, xử lý trả lời muộn và cleanup.
5. Chọn executor phù hợp, đo queue/rejection, áp dụng cơ chế truyền context và kiểm soát transaction.
6. Thử các trường hợp không có listener, listener ném exception, timeout, nhiều event đồng thời và shutdown.
7. Nếu tính đúng đắn phụ thuộc xử lý bền vững hoặc nhiều instance, chuyển sang mô hình có lưu trạng thái/acknowledgment thích hợp.

**Ghi nhớ:** `Future` trên một phương thức `@Async` là công cụ để caller **gọi phương thức qua proxy** theo dõi công việc. Khi phương thức đó đồng thời là `@EventListener`, event publisher vẫn chỉ thấy `publishEvent(...)` trả `void`. Muốn nhận kết quả, hãy thiết kế một giao diện phản hồi cụ thể; đừng suy ra một giao diện trả về Future từ việc listener khai báo Future.

## Tài liệu tham khảo

- Spring Framework 6.2 — ApplicationContext, `@EventListener`, Asynchronous Listeners và giới hạn của giá trị trả về: https://docs.spring.io/spring/reference/6.2/core/beans/context-introduction.html
- Spring Framework — `@Async`, `Future`, `CompletableFuture`, `@EnableAsync` và executor: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — `@Async` annotation API: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/Async.html
- Spring Framework — `@EventListener` annotation API: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html
