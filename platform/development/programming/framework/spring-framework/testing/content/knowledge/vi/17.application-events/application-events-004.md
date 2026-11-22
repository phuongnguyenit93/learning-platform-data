# Sự kiện đồng bộ so với xử lý trên executor

Trong Spring, việc phát một application event và việc chạy listener là hai thao tác có liên quan nhưng không đồng nghĩa. Mặc định, Spring gọi listener ngay trên thread đang phát sự kiện. Nếu listener thực hiện công việc chậm, lời gọi phát sự kiện cũng phải chờ. Có thể chuyển listener sang executor để xử lý trên thread pool, nhưng khi đó thời điểm hoàn tất, thứ tự, lỗi và ngữ cảnh transaction đều thay đổi.

Hiểu rõ khác biệt này giúp chọn đúng cách xử lý cho từng loại công việc: tác vụ cần hoàn thành ngay trong luồng nghiệp vụ thường phù hợp với listener đồng bộ; tác vụ phụ trợ có thể chạy độc lập thường phù hợp với executor; còn công việc cần bảo đảm không mất dữ liệu cần một cơ chế lưu trữ và giao nhận bền vững.

## 1. Phát sự kiện và thực thi listener

Spring cho phép một bean phát sự kiện thông qua **ApplicationEventPublisher**. Bean khác đăng ký nhận sự kiện bằng **@EventListener**. Từ Spring Framework 4.2, sự kiện có thể là một object thông thường; không bắt buộc phải kế thừa **ApplicationEvent**.

Ví dụ, khai báo sự kiện khi một đơn hàng được tạo:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(UUID orderId, Instant occurredAt) {
}
~~~

Service phát sự kiện:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void placeOrder(UUID orderId) {
        // Lưu đơn hàng và thực hiện các bước nghiệp vụ cần thiết.
        eventPublisher.publishEvent(
                new OrderPlaced(orderId, Instant.now())
        );
    }
}
~~~

Listener nhận sự kiện:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {

    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        System.out.println(
                "Audit order " + event.orderId()
                        + " on " + Thread.currentThread().getName()
        );
    }
}
~~~

**publishEvent(...)** gửi sự kiện vào ApplicationContext. ApplicationContext dùng **ApplicationEventMulticaster** để tìm và gọi các listener phù hợp. Với cấu hình mặc định, multicaster là **SimpleApplicationEventMulticaster** và không có executor bất đồng bộ được gắn vào nó.

Vì vậy, luồng thực thi mặc định có dạng:

~~~text
Thread gọi OrderService.placeOrder()
    |
    |-- eventPublisher.publishEvent(event)
            |
            |-- ApplicationEventMulticaster
                    |
                    |-- OrderAuditListener.onOrderPlaced(event)
                    |       (cùng thread phát sự kiện)
                    |
                    |-- các listener đồng bộ khác
    |
    |-- publishEvent() trả về
    |
    |-- placeOrder() tiếp tục
~~~

Nếu listener mất 500 ms để hoàn tất, lời gọi **publishEvent(...)** cũng phải chờ khoảng thời gian đó. Nếu có nhiều listener đồng bộ, thời gian chờ có thể gần bằng tổng thời gian chạy của chúng.

## 2. Xử lý đồng bộ theo mặc định

Đồng bộ có nghĩa là bên gọi chỉ tiếp tục sau khi listener được gọi hoàn tất. Nó không có nghĩa là toàn bộ ứng dụng chỉ có một thread; nó chỉ mô tả quan hệ chờ giữa lời gọi phát sự kiện và listener.

Ví dụ:

~~~java
public void placeOrder(UUID orderId) {
    System.out.println("Before publish");

    eventPublisher.publishEvent(
            new OrderPlaced(orderId, Instant.now())
    );

    System.out.println("After publish");
}
~~~

Nếu listener cũng ghi log khi bắt đầu và kết thúc, thứ tự có thể quan sát được là:

~~~text
Before publish
Listener started
Listener finished
After publish
~~~

Các đặc điểm quan trọng:

- Listener chạy trên thread đang gọi **publishEvent(...)**.
- Khi **publishEvent(...)** trả về, các listener đồng bộ đã được gọi xong.
- Các listener được gọi theo thứ tự Spring xác định; có thể dùng **@Order** hoặc **Ordered** để chỉ định thứ tự gọi.
- Nếu listener ném exception và multicaster không có **ErrorHandler**, exception có thể truyền ngược về nơi gọi **publishEvent(...)**; việc dispatch cũng có thể dừng trước các listener tiếp theo.
- Listener có thể sử dụng ngữ cảnh gắn với thread hiện tại, chẳng hạn transaction được quản lý theo thread.

Đồng bộ thường phù hợp khi kết quả listener là một phần của luồng xử lý hiện tại, listener cần hoàn tất trước khi service trả về, hoặc công việc ngắn và có thời gian thực thi dự đoán được. Ví dụ: cập nhật trạng thái nội bộ, kiểm tra quy tắc đơn giản hoặc ghi nhận một thay đổi cần được xác nhận ngay.

Điểm cần cân nhắc là một listener chậm có thể kéo dài request hoặc công việc nền đang phát sự kiện. Listener lỗi cũng có thể làm luồng gọi thất bại nếu lỗi không được xử lý riêng.

## 3. Chuyển listener sang executor

Executor là cơ chế nhận một tác vụ và quyết định cách thực thi tác vụ đó. Executor có thể chạy tác vụ ngay trên thread gọi, tạo thread mới hoặc đưa tác vụ vào thread pool. Do đó, chỉ truyền một executor vào cấu hình chưa đủ để kết luận tác vụ chắc chắn chạy trên thread khác; hành vi thực tế phụ thuộc executor được chọn.

Với Spring, có hai cách thường gặp để chạy event listener trên executor:

1. Dùng **@Async** cho từng listener cần chạy bất đồng bộ.
2. Cấu hình executor cho **SimpleApplicationEventMulticaster** để multicaster gửi các listener đủ điều kiện sang executor.

Hai cách này tác động ở hai điểm khác nhau. Hãy chọn cách phù hợp với phạm vi muốn bất đồng bộ hóa.

### 3.1. Dùng @Async cho từng listener

Khai báo executor và bật hỗ trợ xử lý bất đồng bộ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean("applicationEventExecutor")
    public ThreadPoolTaskExecutor applicationEventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("app-event-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
~~~

Gắn **@Async** lên listener muốn chuyển sang executor:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderNotificationListener {

    @Async("applicationEventExecutor")
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        // Gửi thông báo hoặc thực hiện một tác vụ phụ trợ tốn thời gian.
        System.out.println(
                "Notify order " + event.orderId()
                        + " on " + Thread.currentThread().getName()
        );
    }
}
~~~

Trong ví dụ này, multicaster mặc định vẫn gọi listener trong luồng phát sự kiện. Tuy nhiên, lời gọi đi qua proxy do Spring tạo cho **@Async**; proxy gửi phần thân phương thức sang **applicationEventExecutor**. Sau khi tác vụ được chấp nhận, lời gọi listener trả về và luồng phát sự kiện có thể tiếp tục.

**@EnableAsync** bật cơ chế xử lý **@Async**. Lời gọi phải đi qua bean proxy của Spring; gọi một phương thức **@Async** từ một phương thức khác trong cùng instance (self-invocation) thường không đi qua proxy nên không tạo ra bất đồng bộ như mong đợi. Hãy đặt listener ở một bean Spring riêng và để ApplicationContext gọi bean đó.

Ưu điểm của cách này là chỉ những listener được đánh dấu **@Async** mới được gửi sang executor. Các listener khác tiếp tục chạy đồng bộ.

### 3.2. Cấu hình executor cho SimpleApplicationEventMulticaster

Nếu muốn multicaster gửi các listener đủ điều kiện sang executor, có thể khai báo bean mang tên **applicationEventMulticaster**:

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.task.TaskExecutor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class EventMulticasterConfiguration {

    @Bean(name = "applicationEventMulticaster")
    public SimpleApplicationEventMulticaster applicationEventMulticaster(
            ConfigurableBeanFactory beanFactory,
            @Qualifier("applicationEventExecutor") TaskExecutor executor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster(beanFactory);
        multicaster.setTaskExecutor(executor);
        return multicaster;
    }
}
~~~

Bean này thay thế multicaster mặc định của ApplicationContext. Khi phát sự kiện, multicaster gửi lời gọi của listener đủ điều kiện vào executor đã cấu hình. Những listener không hỗ trợ asynchronous execution vẫn được gọi theo cơ chế đồng bộ. Trong Spring Framework 6.1, các transactional event listener là một ví dụ quan trọng: chúng cần transaction synchronization gắn với thread và không được chuyển tự động sang executor của multicaster.

Cách này có phạm vi ảnh hưởng rộng hơn **@Async**: các listener khác trong cùng ApplicationContext cũng có thể được chạy trên executor. Vì vậy, cần kiểm tra các listener hiện có trước khi áp dụng cấu hình toàn cục.

Không nên đồng thời cấu hình multicaster chạy bất đồng bộ và gắn **@Async** cho cùng một listener nếu không có chủ đích rõ ràng. Khi đó, multicaster có thể gửi lời gọi proxy vào executor lần thứ nhất, rồi proxy lại gửi phần thân phương thức vào executor lần thứ hai. Việc dispatch hai tầng làm luồng chạy và thời điểm hoàn tất khó theo dõi hơn.

## 4. So sánh luồng đồng bộ và luồng dùng executor

| Khía cạnh | Listener đồng bộ mặc định | Listener chạy qua executor |
|---|---|---|
| Thread thực thi | Thread gọi **publishEvent(...)** | Thường là thread của executor; phụ thuộc loại executor và chính sách từ chối tác vụ |
| Thời điểm trả về | Chờ listener đồng bộ hoàn tất | Thường trả về sau khi tác vụ được gửi đi hoặc được chấp nhận |
| Thời gian request | Bao gồm thời gian listener chạy | Có thể giảm thời gian chờ của request |
| Exception trong listener | Có thể truyền về nơi gọi nếu không cấu hình **ErrorHandler** | Không truyền về thread phát sự kiện theo cùng cách; cần cơ chế xử lý lỗi của executor/listener |
| Thứ tự | Có thể điều khiển thứ tự gọi bằng **@Order** | Thứ tự gửi tác vụ không bảo đảm thứ tự hoàn tất |
| Transaction hiện tại | Có thể tham gia transaction đang gắn với thread | Thread khác không tự tham gia transaction của thread phát sự kiện |
| Thread-local context | Dùng ngữ cảnh của thread hiện tại | Không tự động kế thừa các giá trị thread-local |
| Vòng đời tác vụ | Hoàn tất trước khi luồng gọi tiếp tục | Phụ thuộc queue, thread pool và quá trình shutdown |

Một executor không đồng nghĩa với một hàng đợi bền vững. Tác vụ trong thread pool thường chỉ tồn tại trong bộ nhớ của tiến trình. Nếu ứng dụng dừng đột ngột, tác vụ đang chờ có thể mất. Nếu queue đầy, executor có thể từ chối tác vụ hoặc áp dụng chính sách khác như chạy tác vụ trên thread gọi.

## 5. Các khác biệt cần xử lý trong ứng dụng thực tế

### 5.1. Exception và kết quả xử lý

Với listener đồng bộ, nơi gọi có thể nhận được exception trực tiếp từ **publishEvent(...)** nếu listener lỗi và multicaster không cấu hình **ErrorHandler**. Điều này có thể phù hợp khi listener là một phần bắt buộc của nghiệp vụ.

Với listener chạy bằng **@Async**, exception xảy ra sau khi tác vụ được gửi đi nên không thể truyền ngược về thread đã phát sự kiện như một lời gọi đồng bộ. Với phương thức trả về **void**, hãy cấu hình **AsyncUncaughtExceptionHandler** nếu cần xử lý tập trung. Với multicaster có executor, có thể cấu hình **ErrorHandler** trên multicaster để xử lý lỗi khi listener được gọi.

Ngoài lỗi trong listener, cần quan tâm trường hợp executor từ chối tác vụ. Ví dụ, queue đã đầy và chính sách từ chối là ném exception. Khi đó, việc gửi tác vụ có thể thất bại ngay trong lúc phát sự kiện. Chính sách từ chối kiểu chạy tác vụ trên thread gọi có thể khiến một số lần phát sự kiện quay lại hành vi chờ đồng bộ.

Không nên chỉ ghi log rồi bỏ qua lỗi nếu tác vụ có ý nghĩa nghiệp vụ. Hãy xác định rõ có cần retry, lưu trạng thái thất bại, cảnh báo vận hành hoặc cho phép người dùng thực hiện lại hay không.

### 5.2. Thứ tự listener và thứ tự hoàn tất

**@Order** có thể xác định thứ tự Spring gọi hoặc gửi các listener. Khi các listener chạy đồng bộ, listener có order nhỏ hơn được gọi trước và phải hoàn tất trước khi luồng gọi chuyển sang listener tiếp theo.

Khi các listener được gửi sang thread pool, việc gửi theo thứ tự không có nghĩa là chúng hoàn tất theo thứ tự đó. Một listener xử lý nhanh có thể kết thúc trước listener đã được gửi trước nó. Nếu nghiệp vụ yêu cầu thứ tự xử lý nghiêm ngặt, hãy thiết kế một luồng xử lý tuần tự hoặc một cơ chế partition/queue có bảo đảm thứ tự phù hợp.

### 5.3. Transaction và thời điểm commit

Transaction của Spring thường được gắn với thread hiện tại. Listener đồng bộ được gọi trong thread của service có thể tham gia transaction hiện hành, tùy cấu hình transaction manager và propagation.

Khi listener chạy trên thread pool, transaction của thread phát sự kiện không tự động được truyền sang thread mới. Có thể xảy ra các tình huống:

- Listener chạy trước khi transaction của service commit.
- Listener không nhìn thấy dữ liệu chưa commit từ transaction ban đầu.
- Transaction ban đầu rollback nhưng listener bất đồng bộ đã thực hiện tác vụ bên ngoài.
- Listener cần ghi dữ liệu phải mở transaction riêng nếu nghiệp vụ yêu cầu.

Nếu chỉ muốn xử lý sự kiện sau khi transaction commit, dùng **@TransactionalEventListener**:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderAfterCommitListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlaced event) {
        // Chỉ xử lý khi transaction phát sự kiện đã commit.
    }
}
~~~

Mặc định, transactional event listener chỉ được gọi khi có transaction phù hợp đang hoạt động tại thời điểm phát sự kiện. Nếu không có transaction, listener sẽ không được gọi, trừ khi bật **fallbackExecution**.

Nếu cần xử lý bất đồng bộ sau commit, có thể kết hợp listener gắn với transaction và cơ chế **@Async** một cách có chủ đích. Phần thân xử lý chạy ở thread khác và không kế thừa transaction đã commit; nếu cần ghi dữ liệu, hãy mở transaction mới phù hợp. Đặc biệt, đừng kỳ vọng cấu hình executor toàn cục của multicaster sẽ tự chuyển transactional event listener sang thread pool.

### 5.4. Thread-local context

Các dữ liệu gắn với thread như MDC dùng cho log, **SecurityContext**, request context hoặc thông tin transaction không tự động xuất hiện trên thread của executor. Nếu listener cần những dữ liệu này, hãy truyền dữ liệu nghiệp vụ cần thiết trực tiếp trong event hoặc cấu hình cơ chế truyền context phù hợp, chẳng hạn **TaskDecorator** cho executor.

Không nên truyền cả đối tượng request hoặc các đối tượng có vòng đời ngắn sang tác vụ chạy sau request nếu chúng không được thiết kế để dùng ngoài request. Event nên chứa dữ liệu cần thiết và có vòng đời rõ ràng.

### 5.5. Queue, giới hạn tài nguyên và shutdown

Thread pool cần giới hạn số thread và dung lượng queue. Queue không giới hạn có thể làm bộ nhớ tăng liên tục khi tốc độ phát sự kiện cao hơn tốc độ xử lý. Pool quá lớn có thể gây tranh chấp CPU, kết nối database hoặc các tài nguyên dùng chung.

Khi thiết kế executor, cần xác định:

- Số thread đồng thời phù hợp với loại tác vụ.
- Dung lượng queue tối đa.
- Chính sách khi queue đầy.
- Thời gian chờ khi ứng dụng shutdown.
- Cách theo dõi số tác vụ đang chạy, queue, tác vụ bị từ chối và thời gian xử lý.

**setWaitForTasksToCompleteOnShutdown(true)** và **setAwaitTerminationSeconds(...)** giúp Spring chờ một khoảng thời gian để tác vụ đang chạy hoàn tất khi shutdown. Chúng không biến thread pool thành hệ thống lưu trữ bền vững và không bảo đảm tác vụ sẽ sống sót qua sự cố tiến trình hoặc máy chủ.

## 6. Kiểm thử listener đồng bộ và bất đồng bộ

Khi kiểm thử, cần xác nhận cả hành vi chức năng lẫn cách listener được thực thi. Không nên dùng **Thread.sleep(...)** để chờ tác vụ bất đồng bộ vì thời gian chờ cố định có thể làm test chậm và không ổn định. Có thể dùng **CountDownLatch**, **CompletableFuture** hoặc Awaitility để đồng bộ test với tác vụ.

Với listener đồng bộ, có thể ghi lại tên thread và kiểm tra ngay sau khi phát sự kiện:

~~~java
String publishingThread = Thread.currentThread().getName();

eventPublisher.publishEvent(
        new OrderPlaced(orderId, Instant.now())
);

assertEquals(publishingThread, listenerThreadName.get());
~~~

Với listener dùng **@Async**, listener có thể ghi lại tên thread rồi đếm latch:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.scheduling.annotation.Async;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class AsyncOrderProbe {

    private final CountDownLatch completed = new CountDownLatch(1);
    private final AtomicReference<String> threadName = new AtomicReference<>();

    @Async("applicationEventExecutor")
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        threadName.set(Thread.currentThread().getName());
        completed.countDown();
    }

    public CountDownLatch completed() {
        return completed;
    }

    public String threadName() {
        return threadName.get();
    }
}
~~~

Test có thể chờ listener hoàn tất rồi so sánh thread:

~~~java
String publishingThread = Thread.currentThread().getName();

eventPublisher.publishEvent(
        new OrderPlaced(orderId, Instant.now())
);

assertTrue(asyncOrderProbe.completed().await(2, TimeUnit.SECONDS));
assertNotEquals(publishingThread, asyncOrderProbe.threadName());
~~~

Ví dụ trên minh họa cách kiểm tra; trong test suite thực tế, hãy tạo lại latch và trạng thái probe cho từng lần kiểm thử để tránh trạng thái từ test trước ảnh hưởng test sau. Giới hạn thời gian chờ nên đủ rộng cho môi trường CI nhưng vẫn hữu hạn để test không treo.

Các trường hợp nên kiểm thử:

1. Listener đồng bộ hoàn tất trước khi service tiếp tục.
2. Listener **@Async** được gọi trên executor dự kiến.
3. Exception của listener được xử lý theo cấu hình đã chọn.
4. Queue đầy hoặc executor từ chối tác vụ được xử lý rõ ràng.
5. Listener có phụ thuộc transaction được chạy ở đúng phase.
6. Test có **@Transactional** không vô tình rollback khiến **AFTER_COMMIT** listener không được kích hoạt. Test transaction mặc định thường rollback khi kết thúc; nếu cần kiểm tra sau commit, hãy chủ động commit transaction trong test.

Không chỉ kiểm tra rằng listener đã được gọi. Với listener bất đồng bộ, hãy kiểm tra thêm thread thực thi, thời điểm hoàn tất và hành vi khi lỗi xảy ra.

## 7. Chọn cách xử lý phù hợp

| Nhu cầu | Cách phù hợp |
|---|---|
| Listener ngắn, cần hoàn tất trước khi service trả về | **@EventListener** đồng bộ mặc định |
| Chỉ một vài listener phụ trợ được phép chạy nền | **@Async** trên từng listener |
| Hầu hết listener trong một ApplicationContext cần executor | Cấu hình executor cho **SimpleApplicationEventMulticaster**, sau khi kiểm tra listener đặc biệt |
| Chỉ xử lý sau khi transaction commit | **@TransactionalEventListener(phase = AFTER_COMMIT)** |
| Xử lý sau commit và không làm chậm thread commit | Transactional listener kết hợp cơ chế async được cấu hình và kiểm thử rõ ràng |
| Tác vụ bắt buộc phải được giao nhận lại sau khi ứng dụng restart | Durable queue, message broker hoặc Transactional Outbox |
| Cần thứ tự xử lý theo một khóa nghiệp vụ | Queue/partition hoặc worker tuần tự theo khóa |

Application event của Spring chủ yếu phục vụ giao tiếp trong cùng ApplicationContext và cùng tiến trình. Dùng executor chỉ thay đổi cách thực thi trong tiến trình đó; nó không cung cấp lưu trữ bền vững, retry sau restart, xác nhận giao nhận hay giao tiếp giữa nhiều service.

Nếu một sự kiện đại diện cho nghĩa vụ nghiệp vụ không được phép mất, ví dụ yêu cầu gửi hóa đơn, trừ tiền hoặc đồng bộ trạng thái đơn hàng sang hệ thống khác, hãy cân nhắc Transactional Outbox hoặc message broker. Với Outbox, ứng dụng ghi dữ liệu nghiệp vụ và bản ghi cần phát trong cùng transaction; một tiến trình riêng đọc bản ghi đó và gửi đi, có cơ chế retry và đánh dấu trạng thái.

## 8. Những nhầm lẫn thường gặp

- **Gọi publishEvent(...) không có nghĩa là bất đồng bộ.** Mặc định listener được gọi đồng bộ trên thread phát sự kiện.
- **@EventListener không tự tạo thread mới.** Muốn chạy bằng executor cho một listener, dùng **@Async** và bật **@EnableAsync**, hoặc cấu hình multicaster.
- **Có executor không đồng nghĩa luôn chạy trên thread khác.** Executor có thể chạy trực tiếp trên thread gọi; chính sách từ chối cũng có thể khiến tác vụ chạy trên thread gọi.
- **@Order không bảo đảm thứ tự hoàn tất khi chạy song song.** Nó chỉ giúp xác định thứ tự gọi hoặc gửi listener.
- **Transaction không tự truyền qua thread pool.** Thread xử lý mới cần transaction riêng nếu có thao tác cần transaction.
- **Thread pool không phải message broker.** Queue trong bộ nhớ không bảo đảm tác vụ tồn tại sau khi tiến trình dừng.
- **@Async không làm exception quay lại nơi phát event.** Cần thiết kế nơi nhận và xử lý lỗi phù hợp.
- **Không nên bất đồng bộ hóa mọi listener theo mặc định.** Chọn phạm vi async theo thời gian xử lý, quan hệ phụ thuộc, yêu cầu transaction và mức độ quan trọng của tác vụ.

## 9. Kết luận

Spring application event chạy đồng bộ theo mặc định: thread phát sự kiện gọi listener và chờ listener hoàn tất. **@Async** chuyển riêng listener được đánh dấu sang executor; executor của **SimpleApplicationEventMulticaster** thay đổi cách dispatch cho các listener đủ điều kiện.

Khi chuyển từ đồng bộ sang executor, cần thiết kế lại cách quan sát lỗi, thứ tự hoàn tất, transaction, thread-local context, giới hạn queue và shutdown. Hãy giữ xử lý đồng bộ cho công việc cần kết quả ngay trong luồng hiện tại, dùng executor cho tác vụ phụ trợ có thể tách rời, và dùng cơ chế giao nhận bền vững khi nghiệp vụ yêu cầu không mất sự kiện.
