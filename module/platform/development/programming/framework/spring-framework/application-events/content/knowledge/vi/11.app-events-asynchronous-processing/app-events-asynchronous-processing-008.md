# Không dùng giá trị trả về để phát event tiếp theo trong listener bất đồng bộ

## 1. Vấn đề cần hiểu

Trong Spring Framework Application Events, một listener có thể tạo ra sự kiện mới sau khi xử lý sự kiện đầu vào. Với phương thức `@EventListener` **đồng bộ**, Spring có hỗ trợ đặc biệt: nếu phương thức trả về một đối tượng, Spring xem giá trị trả về đó là sự kiện mới và phát tiếp nó. Tuy nhiên, **cơ chế phát sự kiện bằng giá trị trả về không được hỗ trợ đối với asynchronous event listener**.

Ví dụ quy trình đơn hàng:

```text
OrderSubmitted
    |
    v
Xác nhận đơn hàng
    |
    v
OrderAccepted
    |
    v
Chuẩn bị thông báo bất đồng bộ
    |
    v
NotificationRequested
    |
    v
Listener gửi thông báo
```

Giả sử bước “chuẩn bị thông báo” dùng `@Async` để chạy trên thread pool. Không thể viết nó như một listener đồng bộ trả về `NotificationRequested` rồi mặc nhiên trông đợi Spring phát tiếp. **Cách đúng** là inject `ApplicationEventPublisher` và gọi `publisher.publishEvent(new NotificationRequested(...))` tại thời điểm muốn phát sự kiện tiếp theo.

Đây là giới hạn cụ thể của cơ chế **kết quả trả về của `@EventListener`**, không phải lệnh cấm phát sự kiện bên trong listener bất đồng bộ. Một listener `@Async` vẫn có thể phát sự kiện mới **tường minh**.

## 2. So sánh hai cơ chế phát sự kiện

| Đặc điểm | Listener đồng bộ | Listener bất đồng bộ |
| --- | --- | --- |
| Khai báo điển hình | `@EventListener` | `@Async @EventListener` |
| Luồng thực thi | Thường là luồng gọi `publishEvent` trong cấu hình mặc định | Luồng executor được Spring chọn |
| Trả về một event để Spring tự phát tiếp | **Được hỗ trợ** | **Không được hỗ trợ** |
| Trả về Collection/array chứa nhiều event để tự phát từng phần tử | **Được hỗ trợ** với listener đồng bộ | **Không áp dụng** cho listener bất đồng bộ |
| Phát event mới bằng `ApplicationEventPublisher` | Được hỗ trợ | **Được hỗ trợ và là cách cần dùng** |
| Lỗi từ thân phương thức | Với dispatch đồng bộ mặc định, lỗi chưa xử lý có thể lan tới publisher | Lỗi trong `@Async void` không tự lan về publisher |
| Bảo đảm đã xử lý xong khi `publishEvent` ban đầu trả về | Thường có cho đường gọi đồng bộ mặc định | Không có đối với phần việc được gửi vào executor |

Điểm quan trọng: cơ chế “`return new SomeEvent(...)`” là **tiện ích do adapter của `@EventListener` thực hiện**, không phải chức năng chung của mọi phương thức Java hay mọi đối tượng `ApplicationListener`. Một `ApplicationListener<E>` theo interface vốn có phương thức `void onApplicationEvent(E event)`.

### 2.1. Mẫu đúng với listener đồng bộ

```java
@EventListener
public OrderAccepted accept(OrderSubmitted event) {
    // Kiểm tra/xác nhận đơn trong xử lý đồng bộ.
    return new OrderAccepted(event.orderId());
}
```

Khi Spring gọi phương thức `@EventListener` này và nhận `OrderAccepted`, adapter có thể công bố kết quả như một event mới. Listener khác đăng ký cho `OrderAccepted` sẽ được xét để thực thi.

Nếu phương thức đồng bộ trả về một `Collection` hay mảng sự kiện, Spring phát **từng phần tử** như sự kiện riêng. Không nên dùng cơ chế này như một cách biểu đạt workflow nhiều bước có ràng buộc phức tạp: nó chỉ mô tả việc phát các event kết quả.

### 2.2. Mẫu sai với listener bất đồng bộ

```java
// PHẢN VÍ DỤ: không sử dụng kiểu thiết kế này.
@Async("eventWorker")
@EventListener
public NotificationRequested wrong(OrderAccepted event) {
    return new NotificationRequested(event.orderId());
}
```

Đoạn trên **không phải ví dụ chạy hợp lệ**. `@Async` trong chế độ proxy thông thường yêu cầu kiểu trả về `void` hoặc loại `Future` được hỗ trợ; một kiểu trả về nghiệp vụ như `NotificationRequested` là không phù hợp với hợp đồng phương thức bất đồng bộ. Quan trọng hơn, Spring cũng **không hỗ trợ tự phát event từ giá trị trả về của asynchronous listener**.

Đổi sang `CompletableFuture<NotificationRequested>` không biến nó thành cơ chế tự phát `NotificationRequested`. Future biểu diễn kết quả của công việc async; nếu muốn phát tiếp event, phải có lời gọi publish tường minh.

### 2.3. Mẫu đúng với listener bất đồng bộ

```java
// Bên trong một Spring bean có @EnableAsync được kích hoạt.
private final ApplicationEventPublisher publisher;

@Async("eventWorker")
@EventListener
public void prepareNotification(OrderAccepted event) {
    // Thực hiện công việc bất đồng bộ.
    publisher.publishEvent(
            new NotificationRequested(event.orderId()));
}
```

Đây là trích đoạn thiết kế: `publisher` cần được inject, các kiểu sự kiện cần được định nghĩa và executor `eventWorker` cần tồn tại. Ví dụ đầy đủ ở mục 4.

Phương thức trả về `void`. Sự kiện mới được phát **ở dòng gọi `publisher.publishEvent(...)`**. Nếu xử lý thất bại trước dòng đó và không có cơ chế bù/retry, event mới sẽ không được phát. Cách viết tường minh giúp thể hiện chính xác “khi nào” phát tiếp event và dễ gắn chính sách lỗi.

## 3. Luồng xử lý thật sự diễn ra như thế nào?

Có hai thao tác khác nhau thường bị gộp lại:

1. **Phát sự kiện đầu tiên:** một thành phần gọi `ApplicationEventPublisher.publishEvent(orderSubmitted)`.
2. **Phát sự kiện tiếp theo:** một listener xử lý xong một phần công việc rồi quyết định gọi `publisher.publishEvent(notificationRequested)`.

Với listener đồng bộ, Spring có thể thực hiện thao tác thứ hai hộ bạn nếu phương thức `@EventListener` trả về một event. Với listener bất đồng bộ, **chính mã listener** phải thực hiện thao tác phát tiếp.

```text
Luồng publisher                     Luồng executor
-----------------                   --------------------------
publishEvent(OrderSubmitted)
       |
       v
@EventListener đồng bộ
return OrderAccepted
       |
       v
Spring phát OrderAccepted
       |
       +------> @Async @EventListener -> chuẩn bị dữ liệu
                    (schedule)             |
       |                                   v
publishEvent ban đầu                publisher.publishEvent(
có thể đã trả về                      NotificationRequested)
                                           |
                                           v
                                    Listener NotificationRequested
```

**Một chi tiết về thread:** với cấu hình `SimpleApplicationEventMulticaster` mặc định đồng bộ, khi một listener `@Async` gọi `publishEvent` trên **luồng worker**, các listener đồng bộ của event mới cũng thường chạy trên **chính luồng worker đó**. Không nên hiểu “event tiếp theo” tự động chuyển về luồng ban đầu. Nếu multicaster hoặc listener đích có cấu hình async riêng, hành vi luồng sẽ khác.

**Một chi tiết về thời gian:** `publishEvent` được gọi bên trong listener `@Async` có thể xảy ra sau khi phương thức publish ban đầu đã trả về. Do đó, caller không nên suy ra chuỗi sự kiện đã hoàn thành từ việc `publishEvent(OrderSubmitted)` trả về.

## 4. Ví dụ Java 17 và Spring 6.2 có thể chạy

Ví dụ tạo một chuỗi nhỏ để chứng minh rõ hai cơ chế:

- `accept` là `@EventListener` đồng bộ, **trả về** `OrderAccepted`. Spring tự phát event này.
- `prepareNotification` là `@Async @EventListener`, trả về `void` và **gọi `ApplicationEventPublisher` tường minh** để phát `NotificationRequested`.
- `observeNotification` nhận event mới. Chương trình dùng `CountDownLatch` để đợi và kiểm tra thread, tránh đoán thứ tự thực thi.

**Cấu trúc thư mục:**

```text
async-event-followup/
├── pom.xml
└── src/main/java/example/AsyncEventFollowupDemo.java
```

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-event-followup</artifactId>
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
                    <mainClass>example.AsyncEventFollowupDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tệp `src/main/java/example/AsyncEventFollowupDemo.java`:**

```java
package example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncEventFollowupDemo {

    public record OrderSubmitted(String orderId) {}
    public record OrderAccepted(String orderId) {}
    public record NotificationRequested(String orderId) {}

    public static final class Evidence {
        private final AtomicReference<String> acceptedId =
                new AtomicReference<>();
        private final AtomicReference<String> notificationId =
                new AtomicReference<>();
        private final AtomicReference<String> workerThread =
                new AtomicReference<>();
        private final AtomicReference<String> notificationThread =
                new AtomicReference<>();
        private final CountDownLatch finished = new CountDownLatch(1);

        public void awaitNotification() throws InterruptedException {
            if (!finished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timeout waiting for NotificationRequested");
            }
        }
    }

    // Không final: bean này cần được Spring proxy cho @Async.
    public static class OrderListeners {
        private final ApplicationEventPublisher publisher;
        private final Evidence evidence;

        public OrderListeners(ApplicationEventPublisher publisher,
                              Evidence evidence) {
            this.publisher = publisher;
            this.evidence = evidence;
        }

        // Listener đồng bộ: Spring tự phát giá trị trả về.
        @EventListener
        public OrderAccepted accept(OrderSubmitted event) {
            return new OrderAccepted(event.orderId());
        }

        @EventListener
        public void observeAccepted(OrderAccepted event) {
            evidence.acceptedId.set(event.orderId());
        }

        // Listener bất đồng bộ: phải phát event mới tường minh.
        @Async("eventWorker")
        @EventListener
        public void prepareNotification(OrderAccepted event) {
            evidence.workerThread.set(Thread.currentThread().getName());
            publisher.publishEvent(
                    new NotificationRequested(event.orderId()));
        }

        // Với multicaster mặc định đồng bộ, listener này chạy
        // trên thread đã gọi publishEvent(NotificationRequested).
        @EventListener
        public void observeNotification(NotificationRequested event) {
            evidence.notificationId.set(event.orderId());
            evidence.notificationThread.set(
                    Thread.currentThread().getName());
            evidence.finished.countDown();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean
        public Evidence evidence() {
            return new Evidence();
        }

        @Bean
        public OrderListeners orderListeners(
                ApplicationEventPublisher publisher,
                Evidence evidence) {
            return new OrderListeners(publisher, evidence);
        }

        @Bean("eventWorker")
        public ThreadPoolTaskExecutor eventWorker() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-worker-");
            return executor;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        String originalThread = Thread.currentThread().getName();

        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            context.publishEvent(new OrderSubmitted("O-42"));

            Evidence evidence = context.getBean(Evidence.class);
            evidence.awaitNotification();

            String acceptedId = evidence.acceptedId.get();
            String notificationId = evidence.notificationId.get();
            String workerThread = evidence.workerThread.get();
            String downstreamThread = evidence.notificationThread.get();

            System.out.println("Return đồng bộ tạo event: "
                    + "O-42".equals(acceptedId));
            System.out.println("Async publish tường minh tạo event: "
                    + "O-42".equals(notificationId));
            System.out.println("Event tiếp theo trên worker: "
                    + (downstreamThread != null
                            && downstreamThread.startsWith("event-worker-")
                            && downstreamThread.equals(workerThread)
                            && !downstreamThread.equals(originalThread)));
        }
    }
}
```

**Chạy** từ thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

**Kết quả do chương trình in** trong điều kiện executor tiếp nhận và hoàn tất tác vụ:

```text
Return đồng bộ tạo event: true
Async publish tường minh tạo event: true
Event tiếp theo trên worker: true
```

Giải thích:

1. Spring nhận `OrderSubmitted("O-42")`. Phương thức đồng bộ `accept` trả về `OrderAccepted("O-42")`; adapter `@EventListener` phát event đó.
2. `observeAccepted` ghi nhận `O-42`. `prepareNotification` cũng nhận `OrderAccepted` nhưng được gửi sang executor `eventWorker` vì có `@Async("eventWorker")`.
3. Trên luồng `event-worker-*`, `prepareNotification` gọi `publisher.publishEvent(new NotificationRequested("O-42"))`.
4. Trong cấu hình multicaster mặc định, `observeNotification` là listener đồng bộ và nhận event này ngay trên luồng đã gọi `publishEvent`. Nó ghi kết quả rồi nhả latch.
5. `main` chỉ in kết quả sau khi latch hoàn tất. Việc kiểm tra tiền tố và so sánh tên thread cho thấy listener event mới đã chạy trên worker, không dựa vào thứ tự log ngẫu nhiên.

Nếu listener async không chạy kịp trong 10 giây, phương thức `awaitNotification()` ném exception timeout; chương trình **không in ba dòng thành công giả**. Đây là bài demo không cần web server, database hay broker. Các log phụ từ Maven/Spring nếu bật không thuộc ba dòng kết quả trên.

## 5. Vì sao `CompletableFuture` không giải quyết yêu cầu phát tiếp event?

Có thể nghĩ rằng listener async trả về `CompletableFuture<NotificationRequested>` rồi Spring sẽ tự nhận kết quả bên trong Future làm event. **Không nên dựa vào giả định này.** Hợp đồng `@Async` cho phép một số dạng kết quả bất đồng bộ, nhưng cơ chế Spring tự phát **giá trị trả về của `@EventListener`** được tài liệu xác nhận là không hỗ trợ cho listener asynchronous.

Cần tách hai ý nghĩa:

- **Giá trị hoàn thành của Future** biểu thị kết quả tính toán hoặc trạng thái hoàn tất.
- **Sự kiện trong ứng dụng** được chuyển đến các listener khác khi một thành phần gọi `ApplicationEventPublisher.publishEvent(...)` hoặc khi **listener đồng bộ** dùng cơ chế trả về event được Spring hỗ trợ.

Nếu xử lý liên quan Future, vẫn có thể phát event tường minh tại một điểm hoàn thành phù hợp. Ví dụ minh họa tích hợp:

```java
// Giả sử prepareAsync(...) trả về CompletableFuture<Payload>,
// publisher là một ApplicationEventPublisher đã được inject.
prepareAsync(order).whenComplete((payload, error) -> {
    if (error != null) {
        // Ghi nhận thất bại và thực hiện chính sách lỗi/retry.
        return;
    }
    publisher.publishEvent(new NotificationRequested(order.orderId()));
});
```

Đây là đoạn minh họa cần khai báo `prepareAsync`, `order` và các dependency để chạy trong ứng dụng; **không phải phần của ví dụ standalone ở mục 4**. Nó làm rõ publish được gọi trong callback khi công việc hoàn thành thành công. Nếu callback có thể chạy sau khi context đóng, phải thiết kế vòng đời và cơ chế lưu công việc phù hợp.

Không nên gọi `join()` hoặc `get()` trong listener để biến toàn bộ async thành synchronous, nhất là khi tác vụ phụ cũng đang cần cùng một pool một luồng: có thể gây nghẽn hoặc deadlock.

## 6. Khi nào phát sự kiện tiếp theo?

Việc publish tường minh buộc ta xác định chính xác mốc nghiệp vụ.

| Mốc xử lý | Event phù hợp | Lưu ý |
| --- | --- | --- |
| Đơn vừa được chấp nhận hợp lệ | `OrderAccepted` | Phản ánh kết quả xác nhận, không phản ánh email đã gửi |
| Tác vụ chuẩn bị nội dung đã thành công | `NotificationPrepared` | Có thể phát sau khi tạo payload cần gửi |
| Đã yêu cầu hệ thống gửi thông báo | `NotificationRequested` | Chỉ biểu thị **yêu cầu**, chưa chứng minh gửi thành công |
| Nhà cung cấp xác nhận gửi thành công | `NotificationSent` | Chỉ phát sau khi có kết quả đáng tin cậy từ tác vụ gửi |
| Gửi thất bại | `NotificationFailed` | Cần quyết định retry, lưu lỗi và tránh phát vòng lặp vô hạn |

Đặt tên event theo **sự thật đã xảy ra** giúp listener sau hiểu đúng ý nghĩa. Một listener `@Async` vừa nhận `OrderAccepted` đã publish `NotificationSent` trước khi gọi dịch vụ email là sai ngữ nghĩa dù cú pháp Java vẫn hợp lệ.

Nếu một bước nghiệp vụ có nhiều nhánh thành công và thất bại, có thể phát các event khác nhau, nhưng mỗi event nên có dữ liệu đủ để theo dõi: `eventId`, `orderId`, thời điểm, loại kết quả và thông tin correlation khi cần. Không nên truyền mutable entity đang được cập nhật tiếp sang các thread và xem đó là snapshot bất biến.

## 7. Transaction và ranh giới thread

Giả sử mã nguồn phát `OrderSubmitted` khi một transaction chưa commit:

```java
@Transactional
public void submitOrder(String orderId) {
    // Lưu thay đổi nghiệp vụ bằng repository.
    publisher.publishEvent(new OrderSubmitted(orderId));
}
```

Đây là đoạn minh họa tích hợp cần service, repository và transaction manager thật. Nếu listener `@Async` nhận event ngay, phần xử lý trên worker **có thể chạy trước commit**, và dữ liệu vừa lưu có thể chưa hiển thị đối với truy vấn từ transaction khác. Nếu transaction gốc rollback, follow-up event vẫn có thể đã được phát.

Khi tác vụ chỉ được phép chạy **sau khi commit thành công**, cân nhắc:

```java
// Minh họa bên trong Spring bean có @EnableAsync và transaction thật.
@Async("eventWorker")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderAccepted event) {
    publisher.publishEvent(
            new NotificationRequested(event.orderId()));
}
```

Đoạn này cần import `@TransactionalEventListener` và `TransactionPhase` cùng các dependency liên quan. Những điều phải nhớ:

- `@TransactionalEventListener` mặc định dùng phase `AFTER_COMMIT`; với `fallbackExecution = false`, event phát ngoài transaction **không kích hoạt** listener transaction-bound.
- Phần đăng ký callback transaction cần liên hệ với transaction lúc event được phát. Sau khi phase commit thỏa, xử lý `@Async` có thể chuyển việc thực thi sang worker.
- Khi follow-up event được publish **trên worker**, thread này thường **không mang transaction gốc**. Một listener `@TransactionalEventListener` của follow-up event cũng có thể không chạy nếu worker không có transaction hoạt động.
- `AFTER_COMMIT` giải quyết **thời điểm**, không bảo đảm task executor được lưu bền vững. Nếu process chết giữa commit và publish, event tiếp theo có thể không tồn tại.
- Nếu cần vừa commit dữ liệu vừa bảo đảm eventual delivery, cân nhắc **transactional outbox**: ghi trạng thái và outbox record trong cùng transaction, sau đó worker đọc outbox để publish/deliver với retry và idempotency.

Đừng suy ra `ThreadLocal`, MDC, security context, transaction hay persistence context tự chuyển theo từ publisher sang `@Async`. Đưa định danh nghiệp vụ và correlation ID vào event, dùng cơ chế context propagation có chủ đích nếu cần.

## 8. Lỗi, retry và độ tin cậy

Cần tách ba điểm có thể hỏng:

1. **Listener ban đầu bị lỗi trước `publishEvent`:** follow-up event chưa được phát. Với `@Async void`, exception trong thân phương thức không tự truyền về caller; cấu hình `AsyncUncaughtExceptionHandler` hoặc xử lý lỗi rõ ràng.
2. **Executor từ chối task:** listener async có thể chưa bắt đầu. Ví dụ `ThreadPoolTaskExecutor` quá tải có thể phát sinh `TaskRejectedException` khi chuyển task. Cần quan sát và xử lý tình huống này riêng.
3. **Listener của follow-up event thất bại:** việc gọi `publisher.publishEvent(...)` không đồng nghĩa tất cả bên nhận đã xử lý thành công. Với multicaster đồng bộ, exception chưa được xử lý ở listener đích có thể quay về worker đang publish; với multicaster bất đồng bộ, lỗi có thể được xử lý tại executor khác.

Các chiến lược cần xem xét:

- **Idempotency:** một `eventId` hoặc khóa nghiệp vụ cho phép bỏ qua tác dụng phụ đã xử lý nếu task được retry.
- **Retry có giới hạn:** chọn số lần thử, khoảng chờ, điều kiện retry, và nơi ghi lại lỗi cuối cùng. Tránh listener tự phát lại chính event gây vòng lặp không giới hạn.
- **Lưu bền vững:** `ApplicationEventPublisher` phân phối sự kiện nội bộ context, không phải message broker hoặc durable queue. Với quy trình quan trọng, kết hợp outbox/broker.
- **Observability:** log `eventId`/`orderId`, thời điểm nhận và phát follow-up, thread name, trạng thái và thời gian chờ.
- **Dừng ứng dụng:** chính sách shutdown của executor cần cân nhắc task đang chạy và đang chờ; chỉ shutdown “êm” không tự bảo đảm khôi phục khi process crash.

Không khắc phục mất event bằng cách chỉ tăng số luồng hoặc kích thước queue: các tham số đó điều chỉnh khả năng thực thi trong bộ nhớ, không cung cấp tính bền vững.

## 9. Kiểm thử đúng cơ chế phát event tiếp theo

Với ví dụ ở mục 4, test cần chứng minh cả **có event mới** và **event đã được phát đúng cách**.

| Trường hợp | Kỳ vọng |
| --- | --- |
| Listener `accept` đồng bộ trả về `OrderAccepted` | Listener của `OrderAccepted` được gọi |
| Listener `prepareNotification` có `@Async` | Nó thực thi trên luồng `event-worker-*` |
| Listener async gọi `publisher.publishEvent(NotificationRequested)` | Listener của `NotificationRequested` được gọi |
| Bỏ lệnh `publisher.publishEvent` trong listener async | Không có `NotificationRequested` do listener đó phát |
| Listener async ném lỗi trước khi publish | Không phát follow-up thành công; lỗi được theo dõi |
| Executor từ chối task | Không đánh dấu workflow hoàn thành; áp dụng chính sách quá tải |
| Phát follow-up ngoài transaction và đích dùng `@TransactionalEventListener` | Mặc định đích transaction-bound không chạy nếu không có transaction |

Đối với test async, `CountDownLatch`, `CompletableFuture` hoặc cơ chế chờ có timeout giúp giảm lỗi chập chờn. Không dùng một lần `Thread.sleep(100)` rồi kết luận “không có event” nếu listener chưa kịp chạy.

### Ba lỗi kiểm thử hay gặp

**Lỗi 1 — kiểm tra ngay sau publish ban đầu:**

```java
publisher.publishEvent(new OrderSubmitted("O-42"));
// Không được kết luận listener async đã hoàn tất chỉ từ dòng này.
```

**Lỗi 2 — chỉ kiểm tra phương thức async đã chạy:** việc listener gốc chạy không chứng minh follow-up đã được phát. Test cần gắn listener/spy ở loại event tiếp theo và xác nhận đúng payload.

**Lỗi 3 — dùng log như bằng chứng thứ tự:** các luồng có thể xen kẽ log. Hãy đợi callback hoàn thành và so sánh dữ liệu được ghi an toàn luồng.

## 10. Các sai lầm phổ biến

1. **Cho rằng `@Async @EventListener` có thể `return new Event()` như listener đồng bộ.** Spring không hỗ trợ cơ chế đó. Dùng `void` và gọi `ApplicationEventPublisher.publishEvent(...)` tường minh.
2. **Nhầm Future với event.** `CompletableFuture<Event>` là kết quả tính toán, không phải lời hứa Spring sẽ tự publish giá trị hoàn tất thành event.
3. **Quên `@EnableAsync`.** Nếu không kích hoạt async support trong Spring thuần, listener có thể chạy khác điều mong đợi và các giả định về thread sẽ sai.
4. **Gọi nội bộ bypass proxy.** `this.asyncMethod(...)` trong cùng bean ở proxy mode mặc định có thể không đi qua `@Async`.
5. **Publish follow-up quá sớm.** Chỉ phát `NotificationSent` khi tác vụ gửi thành công, không phát ngay lúc bắt đầu gửi.
6. **Bỏ qua transaction.** Worker async không tự thấy dữ liệu chưa commit; cần cân nhắc `AFTER_COMMIT`/outbox nếu sự kiện phụ thuộc dữ liệu bền vững.
7. **Coi `publishEvent` là hàng đợi bảo đảm delivery.** Event nội bộ Spring không có durable persistence/retry built-in.
8. **Dựa vào thứ tự listener thay vì mô hình phụ thuộc rõ ràng.** `@Order` nếu dùng không bảo đảm thứ tự hoàn tất của các công việc bất đồng bộ.
9. **Không có xử lý lỗi.** Exception của `@Async void` có thể chỉ được báo qua handler/log, trong khi publisher vẫn trả về bình thường.
10. **Phát vòng lặp sự kiện.** Một listener của `NotificationRequested` lại phát chính `NotificationRequested` liên tục sẽ tạo chuỗi vô hạn nếu không có điều kiện dừng.

## 11. Checklist thiết kế

- Mỗi event đại diện một sự thật hoặc yêu cầu nghiệp vụ có tên rõ ràng.
- Đã phân biệt listener đồng bộ dùng `return` với listener `@Async` cần publish tường minh.
- `ApplicationEventPublisher` được inject vào bean và được gọi **sau bước xử lý thành công**.
- `@EnableAsync` và executor được cấu hình, có giới hạn tài nguyên và giám sát lỗi.
- Event payload đủ thông tin cho xử lý trên thread khác; tránh phụ thuộc entity mutable hay transaction context.
- Test có thời hạn chờ, kiểm tra đúng event mới và điều kiện lỗi, không suy đoán qua log.
- Nếu nghiệp vụ yêu cầu delivery đáng tin cậy, thiết kế outbox/retry/idempotency.
- Đã kiểm tra khả năng event mới kích hoạt listener đồng bộ trên thread worker và ảnh hưởng đến độ trễ/ngoại lệ của worker.

**Kết luận kỹ thuật:** Giá trị trả về của `@EventListener` là một cách phát event tiếp theo dành cho xử lý **đồng bộ**. Với listener bất đồng bộ, sự kiện tiếp theo phải được phát bằng **`ApplicationEventPublisher.publishEvent(...)` tường minh** tại đúng thời điểm nghiệp vụ.

## Tài liệu tham khảo

- [Spring Framework 6.2 — ApplicationContext Events và giới hạn asynchronous listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Javadoc Spring — EventListener](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework — Task Execution và `@Async`](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
