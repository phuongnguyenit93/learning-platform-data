# `SimpleApplicationEventMulticaster` trong Spring Framework

## 1. Vai trò và vị trí trong cơ chế Application Events

`SimpleApplicationEventMulticaster` là cách triển khai mặc định của giao diện `ApplicationEventMulticaster` trong Spring `ApplicationContext`. Nhiệm vụ của nó là **tìm các listener phù hợp với một sự kiện và chuyển sự kiện đến các listener đó**. Nó kế thừa `AbstractApplicationEventMulticaster`, nơi cung cấp cơ chế đăng ký, quản lý và lọc listener.

Các thành phần cần phân biệt:

- **Publisher**: mã ứng dụng gọi `ApplicationEventPublisher.publishEvent(event)` hoặc `ApplicationContext.publishEvent(event)`.
- **ApplicationContext**: tiếp nhận yêu cầu phát sự kiện và ủy quyền cho multicaster của context.
- **`SimpleApplicationEventMulticaster`**: chọn listener tương thích với kiểu sự kiện và quyết định cách gọi từng listener.
- **Listener**: bean triển khai `ApplicationListener<E>` hoặc phương thức được đánh dấu `@EventListener`; thực hiện nghiệp vụ khi nhận sự kiện.

Luồng xử lý thông thường sau khi context đã khởi tạo:

```text
Service -> publishEvent(event)
        -> ApplicationContext
        -> ApplicationEventMulticaster.multicastEvent(...)
        -> lọc các ApplicationListener phù hợp
        -> gọi từng listener (đồng bộ hoặc qua Executor)
```

Mỗi `ApplicationContext` có multicaster riêng. Nếu không khai báo bean có tên chính xác `applicationEventMulticaster`, Spring tạo một `SimpleApplicationEventMulticaster` mặc định. Bean custom có tên khác sẽ không tự động thay thế multicaster của context.

**Phạm vi:** Đây là cơ chế truyền sự kiện **trong cùng ứng dụng/context**, không phải message broker. Nó không tự lưu sự kiện bền vững, không bảo đảm giao hàng khi tiến trình chết, không cung cấp retry, dead-letter queue hay truyền sự kiện giữa nhiều service. Khi cần các đặc tính đó, cân nhắc Spring Integration hoặc hệ thống messaging chuyên dụng.

## 2. Hành vi mặc định: đồng bộ trên luồng phát sự kiện

Khi chưa cấu hình `taskExecutor`, multicaster hoạt động tương đương `SyncTaskExecutor`: mỗi listener được gọi ngay trên **luồng đang gọi `publishEvent()`**.

Ví dụ, nếu luồng `http-nio-8080-exec-1` phát `OrderCreated`, listener mặc định cũng chạy trên luồng ấy. `publishEvent()` chỉ trở về sau khi các listener đồng bộ liên quan hoàn tất hoặc một listener ném lỗi làm ngắt quá trình. Vì vậy listener chậm có thể tăng thời gian phản hồi của request hoặc giữ luồng xử lý giao dịch quá lâu.

Ưu điểm của mặc định đồng bộ là dễ kiểm tra thứ tự và lỗi, đồng thời listener chạy trên cùng luồng nên có thể nhìn thấy ngữ cảnh gắn với luồng tại thời điểm phát sự kiện (chẳng hạn ngữ cảnh giao dịch hoặc MDC, nếu hiện hữu). Không nên mặc định suy ra rằng listener chỉ chạy sau khi giao dịch đã commit: đó là ngữ nghĩa riêng của `@TransactionalEventListener`.

### Ví dụ Java 17+ chạy độc lập: phát và nhận sự kiện đồng bộ

Tạo dự án Gradle với cấu trúc:

```text
spring-event-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/EventDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-event-demo'
```

`build.gradle` (ví dụ cố định với Spring Framework 6.2.12 và JDK 17 trở lên):

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'demo.EventDemo'
}
```

`src/main/java/demo/EventDemo.java`:

```java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventDemo {

    record OrderCreated(String orderId) {}

    static class OrderObserver {
        @EventListener
        public void onOrderCreated(OrderCreated event) {
            System.out.println("listener: " + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        OrderObserver orderObserver() {
            return new OrderObserver();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            System.out.println("before publish");
            context.publishEvent(new OrderCreated("A-42"));
            System.out.println("after publish");
        }
    }
}
```

Chạy với JDK 17+ và Gradle đã cài:

```bash
gradle -q run
```

Kết quả `stdout` của ba lệnh `println`:

```text
before publish
listener: A-42
after publish
```

`OrderCreated` là một Java record thường, không cần kế thừa `ApplicationEvent`. Spring cho phép phát object bất kỳ; bên trong framework có thể bọc object thành `PayloadApplicationEvent` và vẫn định tuyến đúng đến phương thức `@EventListener` nhận `OrderCreated`. Thứ tự ba dòng trên cho thấy listener đồng bộ hoàn tất trước khi `publishEvent()` trả về.

Nếu dùng `ApplicationListener<E>` trực tiếp, `E` thường là kiểu kế thừa `ApplicationEvent`; với payload không kế thừa lớp này có thể dùng `ApplicationListener<PayloadApplicationEvent<OrderCreated>>` hoặc `@EventListener` như ví dụ.

## 3. Những API chính và cách Spring chọn listener

| API | Mục đích |
| --- | --- |
| `multicastEvent(ApplicationEvent event)` | Phân phối sự kiện đến listener tương thích. |
| `multicastEvent(ApplicationEvent event, ResolvableType eventType)` | Phân phối với thông tin kiểu cụ thể, hữu ích khi cần phân giải generic. |
| `setTaskExecutor(Executor executor)` | Đặt chiến lược thực thi listener. Không đặt thì chạy đồng bộ. |
| `setErrorHandler(ErrorHandler handler)` | Chọn cách xử lý `Throwable` do listener ném ra. |
| `addApplicationListener(...)`, `addApplicationListenerBean(...)` | Đăng ký listener (được kế thừa từ lớp nền). |
| `removeApplicationListener(...)` và các API remove khác | Gỡ listener đã đăng ký (kế thừa). |

Khi nhận một sự kiện, multicaster sử dụng kiểu sự kiện thực tế và thông tin `ResolvableType` nếu có để lấy các listener tương ứng. Listener kiểu `ApplicationListener<OrderCreatedEvent>` chỉ được gọi cho các sự kiện phù hợp với kiểu ấy; phương thức `@EventListener` cũng được Spring chuyển thành listener thích hợp thông qua hạ tầng annotation. Không phải chính `SimpleApplicationEventMulticaster` thực hiện quét `@Component` hay đọc mọi annotation trong ứng dụng.

Một số chi tiết hữu ích:

- `@Order` trên phương thức `@EventListener` hoặc giao diện `Ordered` giúp sắp thứ tự **gọi/đưa tác vụ vào executor**. Khi chạy bất đồng bộ, thứ tự **hoàn tất** vẫn không được bảo đảm.
- Một sự kiện có thể có nhiều listener; không có giá trị trả về tổng hợp từ `publishEvent()`.
- Listener có thể phát thêm sự kiện khác. Với mô hình đồng bộ, chuỗi phát sự kiện lồng nhau cần tránh đệ quy vô hạn và thao tác tốn thời gian.
- Khi dùng kiểu generic phức tạp, khai báo kiểu sự kiện rõ ràng hoặc dùng `ResolvableTypeProvider` nếu cần để Spring phân biệt các tham số kiểu.

## 4. Cấu hình `taskExecutor`: chuyển listener đủ điều kiện sang luồng khác

Bạn có thể thay multicaster mặc định bằng bean tên **chính xác** `applicationEventMulticaster` và gắn `ThreadPoolTaskExecutor`. Ví dụ sau là một lớp cấu hình hoàn chỉnh, đặt trong `src/main/java/demo/AsyncEventsConfig.java` của dự án Spring có dependency `spring-context`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class AsyncEventsConfig {

    @Bean
    ThreadPoolTaskExecutor eventTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("app-event-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean(name = AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
    ApplicationEventMulticaster applicationEventMulticaster(
            ThreadPoolTaskExecutor eventTaskExecutor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(eventTaskExecutor);
        multicaster.setErrorHandler(error ->
                System.err.println("Event listener failed: " + error));
        return multicaster;
    }
}
```

Khi dùng ví dụ này, đưa `AsyncEventsConfig.class` vào cấu hình context của ứng dụng (chẳng hạn đăng ký cùng các class configuration khác). Spring quản lý việc khởi tạo và đóng bean `ThreadPoolTaskExecutor`; bạn không cần tự gọi `initialize()` cho bean do Spring quản lý.

**Điểm quan trọng:** Có `Executor` không có nghĩa *mọi* listener đều chạy bất đồng bộ. Từ Spring Framework 6.1, `ApplicationListener.supportsAsyncExecution()` cho multicaster biết listener có cho phép gọi qua executor không. Giá trị mặc định là `true`; listener trả về `false` vẫn phải được gọi trên luồng phát sự kiện. `TransactionalApplicationListener` là ví dụ quan trọng của trường hợp không hỗ trợ chuyển phần đăng ký đồng bộ giao dịch sang luồng khác.

Đường chạy khái quát:

```text
multicastEvent(event)
  └─ với mỗi listener phù hợp:
       ├─ có Executor và supportsAsyncExecution() == true
       │    └─ executor.execute(() -> invokeListener(listener, event))
       └─ không đủ điều kiện trên
            └─ invokeListener(listener, event) trong luồng hiện tại
```

Với listener chạy trong pool, `publishEvent()` thường chỉ chờ đến khi **gửi tác vụ** cho executor, không chờ việc xử lý xong. Thời điểm kết thúc và thứ tự in log của nhiều listener có thể thay đổi giữa các lần chạy. Một số listener vẫn chạy đồng bộ như đã nêu. Cũng cần tính đến chính sách từ chối tác vụ khi pool quá tải hoặc đóng; không thể xem việc gọi `publishEvent()` thành công là bảo đảm nghiệp vụ bất đồng bộ đã hoàn tất.

### Cân nhắc tài nguyên và ngữ cảnh luồng

- Giới hạn số thread và độ dài hàng đợi; đo backlog, độ trễ và tác vụ lỗi. Pool có queue hữu hạn vẫn có thể quá tải.
- Transaction context, `ThreadLocal`, security context, request context và MDC **không tự động** được mang sang thread mới. Nếu cần truyền ngữ cảnh, dùng cơ chế hỗ trợ phù hợp, ví dụ `TaskDecorator`/context propagation, và chỉ truyền dữ liệu cần thiết.
- Không dựa vào session JPA/Hibernate, entity lazy loading hoặc transaction của publisher trong listener ở thread khác. Truyền ID/snapshot dữ liệu cần thiết và mở phạm vi giao dịch riêng nếu nghiệp vụ yêu cầu.
- `@EventListener` thông thường không có cam kết bền vững. Thiết kế idempotency, lưu trữ sự kiện/outbox hay hàng đợi riêng nếu mất tác vụ là không thể chấp nhận.
- Bảo đảm chiến lược shutdown xử lý tác vụ đang chạy trong thời hạn phù hợp; ví dụ trên chỉ chờ tối đa 10 giây, không tạo bảo đảm giao hàng.

## 5. `setErrorHandler`: lỗi đồng bộ và bất đồng bộ khác nhau

Nếu **không** có `ErrorHandler`, một listener đồng bộ ném `RuntimeException` có thể khiến lời gọi `publishEvent()` ném theo và dừng việc phát sự kiện đến các listener tiếp theo trong lần multicast đó. Đây là hành vi cần cân nhắc khi các listener không được phép làm hỏng luồng chính.

Nếu gắn `ErrorHandler`, `SimpleApplicationEventMulticaster` chuyển lỗi listener cho `handleError(Throwable)`. Một handler chỉ log rồi kết thúc sẽ **nuốt lỗi tại ranh giới multicaster**; vì vậy các listener khác có thể tiếp tục được gọi. Nếu handler ném lại lỗi, lời gọi đồng bộ vẫn có thể thất bại. `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` và `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER` là hai chiến lược có sẵn để tham khảo.

Khi listener chạy qua executor, ngoại lệ xảy ra trong tác vụ của thread khác thường **không** quay trở lại ngay luồng gọi `publishEvent()`. Hãy log đủ thông tin sự kiện, gửi metric/alert và thiết kế chính sách retry hoặc bù trừ phù hợp; chỉ in lỗi ra `stderr` như đoạn cấu hình trên là cách minh họa tối giản.

| Cấu hình | Luồng chạy listener đủ điều kiện | Tác động lỗi listener |
| --- | --- | --- |
| Mặc định, không handler | Luồng publisher | Lỗi có thể truyền về publisher và ngắt multicast |
| Đồng bộ, handler log/suppress | Luồng publisher | Handler nhận lỗi; việc gọi listener khác có thể tiếp tục |
| Executor bất đồng bộ, không handler | Thread của pool | Lỗi nằm ở tác vụ/executor, không bảo đảm truyền về publisher |
| Executor bất đồng bộ, handler log/suppress | Thread của pool | Handler ghi nhận lỗi; publisher thường không chờ xử lý |

## 6. Phân biệt với `@Async` và `@TransactionalEventListener`

### `@Async` trên từng listener

Nếu chỉ muốn một phương thức xử lý ở thread khác, thay vì cấu hình toàn bộ multicaster, có thể dùng:

```java
@EnableAsync
@Configuration
class AsyncConfig {
}

@Component
class NotificationListener {
    @Async
    @EventListener
    public void onOrderCreated(OrderCreated event) {
        // Xử lý gửi thông báo trên executor của @Async.
    }
}
```

Đoạn mã này **chỉ minh họa phần cấu hình và listener**, sử dụng kiểu `OrderCreated` từ ứng dụng; cần các import tương ứng (`EnableAsync`, `Configuration`, `Component`, `Async`, `EventListener`) và một Spring context quản lý bean. `@EnableAsync` kích hoạt hạ tầng xử lý `@Async`. Ngoại lệ trong phương thức bất đồng bộ có cơ chế xử lý riêng như `AsyncUncaughtExceptionHandler`; phương thức listener bất đồng bộ không thể dùng giá trị trả về để phát tiếp một sự kiện theo cách của `@EventListener` đồng bộ. Khi đã cấu hình multicaster toàn cục chạy trên pool, cân nhắc tránh xếp thêm `@Async` không cần thiết.

### Listener gắn với giao dịch

`@TransactionalEventListener` mặc định xử lý sự kiện ở pha `AFTER_COMMIT`. Nó cần cơ chế đăng ký callback với transaction đang hoạt động tại lúc phát sự kiện, nên listener dạng transaction-synchronized không được multicaster tự ý chuyển nguyên phần đăng ký sang thread khác. Không có transaction phù hợp thì listener mặc định không chạy, trừ khi chọn `fallbackExecution = true`. Không nên dùng `@EventListener` thông thường và hy vọng nó chỉ chạy sau commit.

Nếu cần gửi email sau khi đơn hàng được commit, một lựa chọn là `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`; nếu còn cần xử lý bất đồng bộ sau commit, thiết kế riêng `@Async`/executor ở bước xử lý sau transaction và quản lý lỗi của bước đó. Với dữ liệu quan trọng phải bảo đảm giao hàng, nên kết hợp transactional outbox hoặc broker có lưu trữ.

## 7. Kiểm thử và các lỗi cấu hình thường gặp

**Kiểm thử đồng bộ:** Phát sự kiện bằng `context.publishEvent(...)`, rồi kiểm tra trạng thái/spy listener ngay sau lời gọi. Trong ứng dụng thực tế, cũng nên kiểm tra tình huống listener ném lỗi và quy tắc rollback nếu có giao dịch.

**Kiểm thử bất đồng bộ:** Không khẳng định thứ tự log hoặc dùng `Thread.sleep(100)` để chờ. Dùng `CountDownLatch`, `CompletableFuture`, Awaitility hay cơ chế đồng bộ có timeout để đợi listener hoàn tất; sau đó xác minh dữ liệu và lỗi. Khi cần tái lập lỗi pool, kiểm tra cả giới hạn hàng đợi và hành vi shutdown.

Các nhầm lẫn thường thấy:

1. **Đặt tên bean sai:** `@Bean("customMulticaster")` không thay `applicationEventMulticaster` mà `ApplicationContext` sử dụng.
2. **Cho rằng `publishEvent()` luôn bất đồng bộ:** mặc định nó là đồng bộ; chỉ listener hỗ trợ async mới được chuyển sang executor đã cấu hình.
3. **Cho rằng `@Order` bảo đảm thứ tự kết thúc trên nhiều thread:** chỉ có thứ tự chọn/triển khai tác vụ, còn thời điểm hoàn tất phụ thuộc lịch chạy.
4. **Nuốt ngoại lệ rồi xem nghiệp vụ thành công:** `ErrorHandler` có thể ghi log và tiếp tục, nhưng thất bại của listener vẫn cần được xử lý và giám sát.
5. **Đọc transaction/MDC trên thread pool như trên thread publisher:** các ngữ cảnh gắn thread không tự mang sang thread khác.
6. **Dùng event nội bộ thay message queue:** multicaster không tự có lưu trữ bền vững, retry, consumer group hoặc đảm bảo chạy trên nhiều instance.
7. **Quên lifecycle của executor:** ứng dụng có thể thoát hoặc shutdown khi tác vụ vẫn đang xử lý; cần cấu hình đóng tài nguyên và timeout.
8. **Trộn `@Async`, executor toàn cục và listener giao dịch mà không phân biệt ranh giới:** cần xác định rõ callback nào chạy ở thread nào và lỗi đi về đâu.

## 8. Khi nào nên dùng?

- **Mặc định đồng bộ:** các phản ứng trong bộ nhớ, ngắn, cần dễ kiểm soát và không gây nghẽn thread.
- **`SimpleApplicationEventMulticaster` + `ThreadPoolTaskExecutor`:** nhiều listener độc lập, đủ điều kiện chạy song song, chấp nhận tính không đồng bộ và có kế hoạch kiểm soát tải/lỗi.
- **`@Async @EventListener`:** chỉ một số listener cần xử lý nền, muốn giữ đa số listener khác đồng bộ.
- **`@TransactionalEventListener`:** hành động phải gắn với kết quả commit/rollback của transaction; lựa chọn pha phù hợp trước khi bàn đến async.
- **Broker/outbox:** sự kiện có giá trị nghiệp vụ cần giao nhận bền vững hoặc đi qua nhiều dịch vụ.

Tài liệu tham khảo chính thức:

- [Spring Framework: `SimpleApplicationEventMulticaster` API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework: ApplicationContext Events, `@EventListener` và multicaster](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework: Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework: `TransactionalApplicationListener` API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalApplicationListener.html)
