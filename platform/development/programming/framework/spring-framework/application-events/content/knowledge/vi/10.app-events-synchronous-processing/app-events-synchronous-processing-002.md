# Publisher chờ listener hoàn tất trong xử lý sự kiện đồng bộ

Trong Spring Framework Application Events, câu lệnh `publisher.publishEvent(event)` thường trông giống một thao tác “gửi thông báo”. Nhưng với cấu hình dispatch đồng bộ mặc định, nó là một **lời gọi có chờ**: Spring gọi các listener phù hợp ngay trên thread đang publish, và câu lệnh `publishEvent(...)` chỉ trở về bình thường sau khi những listener đồng bộ ấy đã thực thi xong. Nếu một listener chạy lâu, publisher cũng phải chờ; nếu listener ném ngoại lệ và không có cơ chế xử lý ngoại lệ riêng, lời gọi publish có thể ném ngoại lệ.

Đây là một đặc tính quan trọng về **thời điểm, hiệu năng, lỗi và transaction**. Hiểu đúng nó giúp tránh việc nghĩ rằng “đã publish” tương đương “đã chuyển công việc sang nền”.

## 1. Hành vi mặc định diễn ra thế nào?

Trong một `ApplicationContext` thông thường, khi không tự thay thế hoặc cấu hình lại bộ phát sự kiện, Spring dùng `SimpleApplicationEventMulticaster` để chuyển sự kiện cho listener. Với cấu hình mặc định, multicaster thực thi các listener đồng bộ trong **thread của người gọi**; về mặt thực hành, hành vi này tương đương sử dụng `SyncTaskExecutor`.

```text
Thread đang chạy nghiệp vụ
        |
        | 1. service gọi publisher.publishEvent(event)
        v
ApplicationEventPublisher
        |
        v
ApplicationEventMulticaster (mặc định: đồng bộ)
        |
        | 2. gọi listener A --------------------+
        |                                      | A thực thi xong
        | <------------------------------------+
        | 3. gọi listener B --------------------+
        |                                      | B thực thi xong
        | <------------------------------------+
        | 4. trả quyền điều khiển cho publisher
        v
Dòng lệnh sau publishEvent(...)
```

Sơ đồ giả định các listener được gọi và **trả về bình thường**. Cách sắp xếp listener có thể chịu ảnh hưởng của `@Order`, nhưng trọng tâm ở đây là **lời gọi publish đang chờ trên cùng một luồng**. Không được diễn giải sơ đồ như một bảo đảm mọi hệ thống, mọi bean hay mọi cấu hình listener đều chạy tuần tự.

Có thể phát biểu hợp đồng một cách chính xác:

> Khi dùng multicaster đồng bộ mặc định và listener được thực thi đồng bộ, nếu `publishEvent(...)` trả về bình thường thì phần thân các listener đồng bộ mà multicaster đã gọi cho sự kiện đó đã kết thúc.

Hợp đồng **không** tự bảo đảm rằng một giao dịch cơ sở dữ liệu đã commit, mọi tác vụ nền do listener tự khởi tạo đã xong, message đã được gửi đến hệ thống ngoài hay các `@TransactionalEventListener(AFTER_COMMIT)` đã thực thi.

### Ba điều cần phân biệt

| Điều quan sát | Có nghĩa gì trong cấu hình đồng bộ mặc định? | Không suy ra được |
| --- | --- | --- |
| Listener được gọi | Spring đang thực thi method nhận sự kiện trên thread publish | Listener đã thành công nếu nó còn chạy hoặc ném lỗi |
| `publishEvent` trở về **bình thường** | Các listener đồng bộ đã được gọi và hoàn tất mà không để ngoại lệ thoát ra | Transaction đã commit; việc async bên trong đã hoàn tất |
| `publishEvent` ném ngoại lệ | Ít nhất một bước trên đường dispatch có lỗi chưa được xử lý | Tất cả listener đều đã chạy; mọi tác động trước lỗi đã được hoàn tác |

## 2. Ví dụ Java 17+: thấy rõ thứ tự trước và sau `publishEvent`

Tạo dự án Gradle tối thiểu với hai file nguồn dưới đây. Ví dụ dùng Spring Framework 6.2.x; riêng API `ApplicationEventPublisher`, `@EventListener` và `AnnotationConfigApplicationContext` cũng quen thuộc trong các dự án Spring Boot.

**`settings.gradle`**

```groovy
rootProject.name = 'sync-application-events'
```

**`build.gradle`**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'

    testImplementation 'org.springframework:spring-test:6.2.9'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'example.events.SyncEventDemo'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

**`src/main/java/example/events/SyncEventDemo.java`**

```java
package example.events;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class SyncEventDemo {

    record InvoiceIssued(String invoiceId) { }

    static class InvoiceListener {
        @EventListener
        public void onInvoiceIssued(InvoiceIssued event) {
            System.out.println("2. Listener bat dau: " + event.invoiceId());
            System.out.println("3. Listener hoan tat: " + event.invoiceId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        InvoiceListener invoiceListener() {
            return new InvoiceListener();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            System.out.println("1. Truoc publish");
            context.publishEvent(new InvoiceIssued("HD-01"));
            System.out.println("4. Sau publish");
        }
    }
}
```

Chạy bằng JDK 17+ và Gradle wrapper của dự án:

```bash
./gradlew run
```

Trên Windows PowerShell, dùng `./gradlew.bat run`. Bốn dòng do `System.out.println` trong ví dụ tạo ra xuất hiện theo thứ tự:

```text
1. Truoc publish
2. Listener bat dau: HD-01
3. Listener hoan tat: HD-01
4. Sau publish
```

Dòng 4 chỉ có thể chạy sau khi method `onInvoiceIssued` kết thúc trong cấu hình này. Không cần `Thread.sleep`, không cần tự tạo thread và cũng không cần listener kế thừa `ApplicationEvent`: Spring hỗ trợ publish một đối tượng Java thông thường, như record `InvoiceIssued`.

**Giải thích từng bước:**

1. `AnnotationConfigApplicationContext` khởi tạo context và đăng ký bean `InvoiceListener`.
2. `@EventListener` khiến method `onInvoiceIssued` nhận sự kiện kiểu `InvoiceIssued`.
3. `context.publishEvent(...)` đi qua multicaster của context; do chưa cấu hình executor bất đồng bộ nên listener được gọi trong cùng thread.
4. Method listener in ra hai dòng, trả về `void`; sau đó `publishEvent(...)` mới trả về và dòng sau publish được thực thi.
5. Đóng context khi kết thúc `try` để giải phóng tài nguyên.

Ví dụ minh họa **thứ tự điều khiển**, chưa đo thời gian chặn. Một listener gọi HTTP, truy vấn database hoặc chờ khóa có thể khiến khoảng thời gian từ dòng 1 đến dòng 4 tăng đáng kể.

## 3. Kiểm thử thực sự rằng publisher đang phải chờ

Test chỉ so sánh thứ tự các dòng log là hữu ích, nhưng có thể mạnh hơn: chủ động **giữ listener đang chạy** rồi xác nhận `publishEvent` vẫn chưa trả về. `CountDownLatch` tạo điểm đồng bộ rõ ràng mà không dựa vào việc “ngủ” một số mili giây.

Tạo file **`src/test/java/example/events/PublisherWaitsTest.java`**:

```java
package example.events;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PublisherWaitsTest.Config.class)
class PublisherWaitsTest {

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    Gate gate;

    record WorkRequested(String id) { }

    static class Gate {
        final CountDownLatch listenerEntered = new CountDownLatch(1);
        final CountDownLatch allowListenerToFinish = new CountDownLatch(1);
        final AtomicBoolean finished = new AtomicBoolean(false);
        final AtomicReference<Thread> listenerThread = new AtomicReference<>();
    }

    static class BlockingListener {
        private final Gate gate;

        BlockingListener(Gate gate) {
            this.gate = gate;
        }

        @EventListener
        public void on(WorkRequested event) {
            gate.listenerThread.set(Thread.currentThread());
            gate.listenerEntered.countDown();

            try {
                if (!gate.allowListenerToFinish.await(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Listener timed out");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Listener interrupted", ex);
            }

            gate.finished.set(true);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        Gate gate() {
            return new Gate();
        }

        @Bean
        BlockingListener blockingListener(Gate gate) {
            return new BlockingListener(gate);
        }
    }

    @Test
    void publishWaitsForSynchronousListener() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        AtomicReference<Thread> publishingThread = new AtomicReference<>();

        try {
            Future<?> publication = executor.submit(() -> {
                publishingThread.set(Thread.currentThread());
                publisher.publishEvent(new WorkRequested("JOB-7"));
            });

            // Đợi đến khi listener đã được gọi và đang chờ được giải phóng.
            assertTrue(gate.listenerEntered.await(5, TimeUnit.SECONDS));

            // Listener chưa kết thúc nên publishEvent cũng chưa trả về.
            assertFalse(gate.finished.get());
            assertFalse(publication.isDone());

            // Cho phép listener trả về; lúc này publisher mới có thể hoàn tất.
            gate.allowListenerToFinish.countDown();
            publication.get(5, TimeUnit.SECONDS);

            assertTrue(gate.finished.get());
            assertSame(publishingThread.get(), gate.listenerThread.get());
        } finally {
            // Giải phóng listener ngay cả khi assertion thất bại.
            gate.allowListenerToFinish.countDown();
            executor.shutdownNow();
        }
    }
}
```

Chạy riêng test:

```bash
./gradlew test --tests "example.events.PublisherWaitsTest"
```

**Kết quả mong đợi:** bài test pass. Đây là một test JUnit, vì vậy không có một chuỗi stdout nghiệp vụ bắt buộc; Gradle báo kết quả task test thành công. Test chứng minh hai điểm:

- Khi listener đang chờ `allowListenerToFinish`, `publication.isDone()` vẫn là `false`. Nghĩa là publish còn bị giữ trong đường dispatch đồng bộ.
- Sau `countDown()`, `publication.get(...)` hoàn tất và `assertSame` chứng minh listener chạy trong chính thread thực hiện lệnh publish, không phải thread JUnit đang đứng ngoài quan sát.

**Vì sao vẫn tạo executor trong test?** Executor ở đây chỉ chuyển **toàn bộ lời gọi publish** sang một thread phụ, để thread JUnit có thể quan sát nó đang bị chặn. Executor này **không cấu hình** `ApplicationEventMulticaster` thành async. Đây là hai khái niệm khác nhau. Test có timeout để khi listener gặp lỗi, CI báo thất bại thay vì treo vô hạn. Các latch và cờ nguyên tử cho phép quan sát xuyên thread có ranh giới bộ nhớ rõ ràng.

Test dành cho **cấu hình dispatch đồng bộ mặc định**; nếu dự án đã chủ đích đổi sang async, yêu cầu đúng cần kiểm thử sẽ khác.

## 4. Một listener chậm làm publisher chậm

Giả sử luồng xử lý HTTP chạy:

```java
orderRepository.save(order);
publisher.publishEvent(new OrderCreated(order.getId()));
return ResponseEntity.accepted().build();
```

Đây chỉ là **trích đoạn** trong một controller/service, chưa phải chương trình độc lập. Nếu có hai listener đồng bộ, một listener mất khoảng 150 ms và listener khác mất khoảng 250 ms, thì riêng các đoạn xử lý ấy khiến thời gian publish xấp xỉ tổng 400 ms (chưa tính chi phí khác). Các số chỉ là **ví dụ giả định để tính toán**, không phải bảo đảm hiệu năng thực tế.

Hậu quả thường gặp:

- API trả lời chậm vì phải chờ xử lý phụ như gửi email, ghi audit hoặc gọi dịch vụ ngoài.
- Thread xử lý yêu cầu bị giữ; lưu lượng cao có thể làm cạn thread phục vụ.
- Một listener có I/O treo hoặc timeout dài khiến publisher chịu cùng độ trễ.
- Những listener thực thi sau có thể bị ảnh hưởng bởi listener trước ném lỗi.

Tuy nhiên, xử lý đồng bộ **có chủ đích** cũng hữu ích. Ví dụ: listener cần cập nhật một trạng thái nội bộ bắt buộc trước khi service tiếp tục, và hệ thống muốn nhận lỗi trực tiếp nếu bước đó thất bại. Khi đó, cần đánh giá liệu logic này nên nằm ngay trong service điều phối hay thực sự phù hợp với sự kiện đồng bộ.

## 5. Ngoại lệ: lỗi của listener ảnh hưởng đến publisher

Theo mặc định của `SimpleApplicationEventMulticaster`, nếu listener đồng bộ ném một unchecked exception và không được xử lý, exception đi ngược về caller của `publishEvent`. Do đó câu lệnh phía sau publish có thể **không được thực thi**.

Ví dụ trích đoạn listener:

```java
@EventListener
public void on(InvoiceIssued event) {
    throw new IllegalStateException("Cannot update invoice index");
}
```

Với multicaster đồng bộ mặc định, đoạn sau có thể bắt lỗi:

```java
try {
    publisher.publishEvent(new InvoiceIssued("HD-01"));
    // Không vào đây khi lỗi listener chưa được xử lý.
} catch (IllegalStateException ex) {
    // Ứng dụng quyết định cách xử lý lỗi nghiệp vụ.
}
```

Hai đoạn trên là **mã minh họa**, cần được đặt vào các bean và có khai báo/import thích hợp. Không nên suy rộng rằng *mọi listener* đều đã hoàn tất khi publish ném ngoại lệ: multicaster có thể dừng xử lý các listener còn lại. Tình trạng phụ thuộc vào cấu hình `ErrorHandler`, thứ tự listener, và cơ chế dispatch. Một `ErrorHandler` tùy chỉnh có thể ghi nhận/nuốt exception; khi đó việc publish trả về bình thường **không chứng minh mọi listener đều thành công**.

Đặc biệt, việc một listener đã cập nhật database hoặc gọi dịch vụ ngoài trước khi listener kế tiếp thất bại **không tự động được hoàn tác**. Hoàn tác phụ thuộc transaction và tính chất hiệu ứng; email hay HTTP request gửi ra ngoài không thể rollback chỉ nhờ `publishEvent`.

## 6. Điểm dễ nhầm: “đồng bộ” không đồng nghĩa “đã commit”

Nếu gọi `publishEvent` **bên trong** một phương thức có `@Transactional`, listener `@EventListener` thông thường có thể chạy ngay trong cùng thread và cùng transaction context trước khi giao dịch commit. Sự kiện được xử lý đồng bộ, nhưng database vẫn có thể rollback sau đó.

Xét cấu trúc minh họa:

```java
@Transactional
public void createOrder(Order order) {
    orderRepository.save(order);
    publisher.publishEvent(new OrderCreated(order.getId()));
    // Transaction thường chưa commit tại thời điểm này.
}
```

Nếu listener gửi email ngay sau khi nhận sự kiện thì người dùng có thể nhận thông báo về đơn hàng sau đó bị rollback. Với yêu cầu **chỉ xử lý khi commit thành công**, dùng cơ chế phù hợp hơn:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendReceipt(OrderCreated event) {
    notificationGateway.send(event.orderId());
}
```

Các đoạn này chỉ minh họa; cần `Order`, `OrderCreated`, repository, gateway và transaction manager thực tế. Khi có transaction đang hoạt động, phần thân listener `AFTER_COMMIT` được gắn với pha **sau khi commit**, vì vậy lệnh `publishEvent` bên trong phương thức transaction **không chờ callback này hoàn tất tại thời điểm publish**. Khi không có transaction, listener loại này mặc định không chạy trừ khi bật `fallbackExecution = true`.

Phân biệt rõ:

| Listener | Thời điểm xử lý thông thường | `publishEvent` có chờ phần thân listener không? |
| --- | --- | --- |
| `@EventListener`, mặc định đồng bộ | Ngay khi sự kiện được publish | Có, nếu listener trả về bình thường |
| `@TransactionalEventListener(AFTER_COMMIT)` trong transaction đang hoạt động | Theo callback sau commit | Không chờ **phần thân callback** ở thời điểm publish |
| `@Async @EventListener` với async đã bật | Tác vụ nền được lên lịch | Không bảo đảm chờ tác vụ nền hoàn tất |
| Listener trên multicaster gắn executor bất đồng bộ | Theo executor, tùy listener hỗ trợ async | Không bảo đảm chờ các công việc đã được đưa vào executor |

Trong Spring Framework hiện đại, các listener transaction-synchronized có thể yêu cầu được dispatch ngay trên thread gốc để **đăng ký** callback transaction; điều này không biến phần thân callback `AFTER_COMMIT` thành xử lý hoàn tất ngay trong `publishEvent`.

## 7. Những cấu hình làm thay đổi tính chất chờ

### A. Dùng `@Async` cho một listener

```java
@Async
@EventListener
public void sendNotification(OrderCreated event) {
    notificationGateway.send(event.orderId());
}
```

Ví dụ này yêu cầu bật Spring async support, chẳng hạn `@EnableAsync`, và có executor phù hợp. Khi đó publish có thể hoàn tất ngay sau việc chuyển lời gọi tới cơ chế async, trong lúc body `sendNotification` còn chạy. Exception từ async listener không tự động được ném về publisher; phải xử lý hoặc giám sát riêng (ví dụ `AsyncUncaughtExceptionHandler`, kết quả Future phù hợp, hệ thống retry).

### B. Cấu hình executor ở multicaster

Spring cho phép đặt tên bean `applicationEventMulticaster` với một `SimpleApplicationEventMulticaster` được gắn `TaskExecutor`. Điều này có thể khiến các listener hỗ trợ async được gửi sang thread khác thay vì gọi trực tiếp; **tác vụ được schedule không có nghĩa tác vụ đã hoàn tất**. Một số listener, đặc biệt listener gắn transaction, có thể yêu cầu chạy trên thread gốc nhằm giữ ngữ cảnh; không được mặc định mọi listener đều sang executor.

### C. Listener tự khởi tạo việc nền

Ngay cả với multicaster đồng bộ, nếu listener chỉ gọi `executor.submit(...)` rồi trả về thì publisher chỉ chờ **listener trả về**, không chờ task được submit. Quy tắc đồng bộ nằm ở *biên lời gọi listener*, không lan sang các công việc ngoài biên mà listener khởi chạy.

### D. Hệ thống phân tán

`ApplicationEventPublisher` là cơ chế sự kiện trong `ApplicationContext` của ứng dụng Spring. Nó không phải message broker phân tán và không bảo đảm một hệ thống bên ngoài đã nhận/ghi dữ liệu. Muốn bảo đảm delivery bền vững qua process hoặc qua mạng cần cơ chế riêng, ví dụ transactional outbox, broker, acknowledgment, idempotency và retry.

## 8. Phương án thiết kế khi publisher không nên phải chờ

Quyết định nên xuất phát từ ý nghĩa nghiệp vụ:

| Nhu cầu | Lựa chọn thường phù hợp | Đổi lại |
| --- | --- | --- |
| Bước bắt buộc để trả kết quả đúng ngay | Gọi service tường minh hoặc event listener đồng bộ có hợp đồng rõ | Tăng latency của publisher, lỗi truyền trực tiếp |
| Tác vụ phụ không cần xong trước HTTP response | `@Async` hoặc queue phù hợp | Cần retry, quan sát lỗi, thời điểm hoàn tất |
| Tác vụ phải xảy ra sau commit | `@TransactionalEventListener(AFTER_COMMIT)` | Gắn với commit, không tự bảo đảm delivery sau crash |
| Sự kiện cần bền vững khi service restart/crash | Outbox + broker/worker, delivery và idempotency | Thêm hạ tầng và trạng thái xử lý |
| Một chuỗi bước bắt buộc theo thứ tự | Service orchestration hoặc event nối tiếp rõ ràng | Tăng tính tường minh, giảm ghép nối ngầm giữa listener |

Đừng thêm async chỉ để giảm latency mà bỏ qua cách quan sát lỗi hoặc thất bại. Ngược lại, đừng giữ một tác vụ chậm trong request thread nếu người dùng không cần chờ nó hoàn thành.

## 9. Kiểm thử những yêu cầu khác nhau

**Yêu cầu: publisher phải đợi listener đồng bộ hoàn tất.** Dùng test latch ở mục 3. Assert `Future` publish chưa hoàn tất khi listener đang bị giữ, và hoàn tất sau khi mở khóa.

**Yêu cầu: exception phải trở về publisher.** Tạo listener ném `IllegalStateException`; `assertThrows(IllegalStateException.class, () -> publisher.publishEvent(event))` trong context mặc định. Không dùng một listener chạy `@Async` cho loại test này.

**Yêu cầu: listener phụ chạy nền không chặn HTTP response.** Dùng latch xác nhận task đã được bắt đầu và cơ chế timeout để quan sát completion. Khi test một luồng async, cần chứng minh response không phụ thuộc completion, thay vì cố định thứ tự thread.

**Yêu cầu: chỉ gửi thông báo sau commit.** Dùng integration test có transaction manager thật; xác nhận chưa gửi trước commit, có gửi sau commit và không gửi khi rollback. Lưu ý test `@Transactional` thường rollback mặc định; có thể dùng `TransactionTemplate` hoặc `TestTransaction` để kiểm soát commit.

**Yêu cầu: mọi listener đều thành công.** Kiểm thử hiệu ứng của từng listener và nhánh lỗi. Đơn thuần thấy `publishEvent` trở về bình thường không đủ khi có custom `ErrorHandler`, async hoặc listener chỉ schedule việc khác.

## 10. Các sai lầm thường gặp

1. **Nghĩ rằng publish là gửi việc vào hàng đợi.** Trong cấu hình đồng bộ mặc định, Spring chạy listener trực tiếp trên thread gọi; publisher chịu toàn bộ thời gian xử lý.
2. **Đo bằng `Thread.sleep` trong test.** Sleep phụ thuộc scheduler và tải CI. `CountDownLatch` hoặc công cụ đồng bộ có timeout mới phản ánh quan hệ trước–sau có thể kiểm chứng.
3. **Tin rằng publish trả về đồng nghĩa database đã commit.** Transaction có thể còn mở; listener thường và listener `AFTER_COMMIT` có pha khác nhau.
4. **Tin rằng chờ listener là chờ mọi I/O nền.** Listener có thể submit task rồi trả về; publisher không theo dõi toàn bộ công việc ấy.
5. **Bỏ qua exception hoặc thời gian chặn.** Listener kém tin cậy có thể kéo chậm request hoặc ngắt chuỗi listener; cần timeout, metric, error strategy và thiết kế transaction rõ ràng.
6. **Lẫn thread tạo publisher với thread chạy method test.** Trong test latch, lệnh publish chạy trên thread executor; listener đồng bộ chạy cùng thread executor đó, còn thread JUnit chỉ quan sát.
7. **Nhầm `@Order` với giải quyết bài toán chờ.** `@Order` ưu tiên lượt gọi listener, không biến công việc async thành đồng bộ hay bảo đảm một transaction đã commit.

## 11. Tự kiểm tra kiến thức

- Nếu listener đồng bộ mất 2 giây, có thể kỳ vọng `publishEvent` trở về sau vài mili giây không? **Không** trong cấu hình mặc định; publisher phải chờ listener.
- Nếu publish diễn ra trong một phương thức `@Transactional`, listener thường đã xong thì transaction chắc chắn commit chưa? **Chưa chắc**; commit có thể ở sau lời gọi publish.
- Nếu listener bật `@Async` nhưng Spring chưa bật hỗ trợ async, có thể tuyên bố listener chạy nền không? **Không**; phải xác nhận cấu hình thực tế.
- Nếu listener ném `IllegalStateException` trong chế độ đồng bộ mặc định và không có `ErrorHandler`, lời gọi publish sẽ thế nào? **Ném exception** về caller; các listener còn lại có thể chưa được gọi.
- Nếu listener đồng bộ chỉ gọi một API trả về `CompletableFuture` rồi kết thúc, publish đã chờ Future đó complete chưa? **Không**, trừ khi chính listener chờ/join Future trước khi trả về.

**Điểm cốt lõi:** Với Spring Application Events đồng bộ mặc định, `publishEvent` là một điểm chờ các **listener đồng bộ được gọi trực tiếp**. Hợp đồng cần quan sát là “listener đã trả về khi publish trả về bình thường”, cùng với ngoại lệ về lỗi, async và pha transaction; không tự mở rộng thành cam kết hoàn tất mọi công việc nghiệp vụ.

## Tài liệu tham khảo chính thức

- [Spring Framework Reference – Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework Javadoc – SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework Reference – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
