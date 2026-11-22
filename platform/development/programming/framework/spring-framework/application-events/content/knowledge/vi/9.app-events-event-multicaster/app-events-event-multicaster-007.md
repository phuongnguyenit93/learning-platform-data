# Thay thế multicaster mặc định trong Spring Framework Application Events

## 1. Mục tiêu và bối cảnh

Trong Spring Framework, các bean phát sự kiện qua `ApplicationEventPublisher.publishEvent(...)`, còn những `ApplicationListener` hoặc phương thức gắn `@EventListener` nhận các sự kiện phù hợp. Thành phần điều phối việc chọn và gọi các listener là **`ApplicationEventMulticaster`**.

Một `ApplicationContext` thông thường sử dụng `SimpleApplicationEventMulticaster` khi không có bean multicaster được người dùng khai báo. Theo mặc định, multicaster này gọi listener **đồng bộ trên luồng phát sự kiện**. Điều đó dễ hiểu và dự đoán được, nhưng một listener xử lý chậm có thể kéo dài thời gian `publishEvent(...)` và giữ luồng của publisher.

Khi cần đổi chính sách phát sự kiện, Spring cho phép khai báo một bean có **đúng tên `applicationEventMulticaster`** và kiểu `ApplicationEventMulticaster`. Context sẽ sử dụng bean ấy thay cho multicaster mặc định. Nhiều yêu cầu phổ biến chỉ cần cấu hình `SimpleApplicationEventMulticaster` sẵn có; không cần tự viết thuật toán phân phối event.

Sau bài này, bạn có thể:

1. Nhận biết sự khác nhau giữa event publisher, multicaster, listener và executor.
2. Thay thế multicaster mặc định bằng một bean Spring có tên chính xác.
3. Cấu hình chạy đồng bộ/bất đồng bộ và `ErrorHandler` ở phạm vi multicaster.
4. Hiểu giới hạn về giao dịch, thứ tự, ngoại lệ, quá tải và vòng đời executor.
5. Viết phép kiểm tra thực tế để xác nhận Spring dùng multicaster mới.

## 2. Cơ chế mặc định và điểm thay thế

Luồng cơ bản:

```text
Bean nghiệp vụ
    |
    | ApplicationEventPublisher.publishEvent(event)
    v
ApplicationContext
    |
    v
ApplicationEventMulticaster
    |
    +--> Listener phù hợp A
    +--> Listener phù hợp B
    +--> Listener phù hợp C
```

Spring xác định listener phù hợp theo kiểu sự kiện và các cơ chế tương ứng như `@EventListener`. Multicaster chịu trách nhiệm **gọi** những listener đã được chọn. Với multicaster mặc định, việc gọi thường diễn ra ngay trong cùng luồng của publisher.

Trong các `ApplicationContext` kế thừa `AbstractApplicationContext`, tên bean hạ tầng được định nghĩa bởi hằng:

```java
AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME
```

Giá trị là `"applicationEventMulticaster"`. Spring tra cứu bean theo **tên đặc biệt này trong context hiện tại**. Nếu không tồn tại bean tương ứng, Spring tạo `SimpleApplicationEventMulticaster` mặc định. Chỉ thêm bean tên `customMulticaster`, dù có kiểu `ApplicationEventMulticaster`, không làm nó trở thành multicaster hạ tầng của context.

Lưu ý rằng đây là cơ chế trong một `ApplicationContext`; ứng dụng có nhiều parent/child context cần xem xét từng context và đường truyền sự kiện riêng, thay vì giả định một bean sẽ tự động cấu hình toàn bộ cây context.

## 3. Chọn đúng mức tùy biến

| Nhu cầu | Cách thực hiện phù hợp | Ý nghĩa |
| --- | --- | --- |
| Giữ cách chạy mặc định | Không khai báo bean `applicationEventMulticaster` | Spring chọn multicaster mặc định, thường đồng bộ |
| Đổi cách xử lý lỗi của listener | Khai báo `SimpleApplicationEventMulticaster` và gọi `setErrorHandler(...)` | Kiểm soát lỗi trong lúc gọi listener |
| Chạy các listener đủ điều kiện trên executor | Khai báo `SimpleApplicationEventMulticaster` và gọi `setTaskExecutor(...)` | Chuyển công việc sang executor được quản lý |
| Chỉ một số listener cần chạy bất đồng bộ | Cân nhắc `@Async` cùng cấu hình async | Tránh thay đổi chính sách toàn cục khi không cần |
| Phân phối sự kiện theo chiến lược hoàn toàn riêng | Cân nhắc triển khai `ApplicationEventMulticaster` hoặc mở rộng class phù hợp | Phải giữ đúng cơ chế đăng ký, lọc, gọi và quản lý listener |

**Quyết định trước khi sửa:** Có thật sự cần đổi chính sách cho các listener trong context hay chỉ cần tối ưu một listener? Tùy biến multicaster là thay đổi ở hạ tầng, ảnh hưởng cả listener ứng dụng và những listener khác đủ điều kiện nhận event trong context.

## 4. Cấu hình tối thiểu: thay bean nhưng vẫn chạy đồng bộ

Nếu mục đích ban đầu chỉ là kiểm soát lỗi, bạn có thể giữ việc gọi listener trên luồng của publisher:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;

@Configuration
class EventMulticasterConfig {
    @Bean(name = AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
    SimpleApplicationEventMulticaster applicationEventMulticaster() {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();

        multicaster.setErrorHandler(error ->
                System.err.println("Lỗi khi xử lý sự kiện: " + error.getMessage()));

        return multicaster;
    }
}
```

Đây là **đoạn cấu hình để thêm vào ứng dụng Spring đã có**, không phải chương trình độc lập. Không gọi `setTaskExecutor(...)` nên multicaster vẫn sử dụng cơ chế gọi đồng bộ theo mặc định.

Hệ quả cần hiểu: `ErrorHandler` trong ví dụ đã **tiêu thụ** exception sau khi ghi thông báo; publisher có thể tiếp tục mà không nhận được exception đó. Chỉ dùng cách này nếu hành vi chấp nhận lỗi đã được thống nhất; ở production nên ghi log với stack trace/metadata phù hợp và đưa lỗi vào hệ thống giám sát. Nếu nghiệp vụ yêu cầu publisher biết lỗi ngay, không nên tùy tiện nuốt exception.

Việc **đặt tên bean** quan trọng hơn tên method Java. Dùng hằng của Spring giúp tránh viết sai chuỗi tên hạ tầng.

## 5. Ví dụ hoàn chỉnh Java 17+: chạy listener bằng một thread pool riêng

Bài toán: Sau khi tạo đơn hàng, gửi một sự kiện `OrderCreated`. Ta muốn listener chạy trên pool có tiền tố luồng `domain-event-`, để việc gọi `publishEvent(...)` không phải trực tiếp thực hiện công việc của listener. Ví dụ dùng `ThreadPoolTaskExecutor` do Spring quản lý, và dùng `CountDownLatch` để quan sát kết quả **không phụ thuộc vào việc thread nào được hệ điều hành lập lịch trước**.

### 5.1. Cấu trúc dự án

```text
custom-multicaster-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/CustomMulticasterDemo.java
```

Nội dung `settings.gradle`:

```groovy
rootProject.name = 'custom-multicaster-demo'
```

Nội dung `build.gradle` (Gradle 8+, Java 17+):

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.CustomMulticasterDemo'
}
```

Spring Framework 6.2.x yêu cầu Java 17 trở lên. Ví dụ dùng trực tiếp `spring-context` để làm nổi bật cơ chế Spring, không đòi hỏi Spring Boot hay web server. Phiên bản `6.2.9` ở đây được cố định để ví dụ có tập phụ thuộc rõ ràng; dự án thực tế nên dùng phiên bản Spring do BOM/build của dự án quản lý.

### 5.2. Chương trình hoàn chỉnh

Lưu vào `src/main/java/demo/CustomMulticasterDemo.java`:

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class CustomMulticasterDemo {

    // Spring có thể phát một object bình thường; không bắt buộc extends ApplicationEvent.
    public record OrderCreated(String orderId) {
    }

    public static class OrderListener {
        private final CountDownLatch handled = new CountDownLatch(1);
        private volatile String handledOrderId;
        private volatile String listenerThreadName;

        @EventListener
        public void onOrderCreated(OrderCreated event) {
            handledOrderId = event.orderId();
            listenerThreadName = Thread.currentThread().getName();
            handled.countDown();
        }

        public boolean awaitHandled() throws InterruptedException {
            return handled.await(5, TimeUnit.SECONDS);
        }

        public String getHandledOrderId() {
            return handledOrderId;
        }

        public String getListenerThreadName() {
            return listenerThreadName;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        ThreadPoolTaskExecutor domainEventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setThreadNamePrefix("domain-event-");
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(20);
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean(name = AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
        SimpleApplicationEventMulticaster applicationEventMulticaster(
                ThreadPoolTaskExecutor domainEventExecutor) {

            SimpleApplicationEventMulticaster multicaster =
                    new SimpleApplicationEventMulticaster();
            multicaster.setTaskExecutor(domainEventExecutor);

            // Minh họa cách gắn xử lý lỗi; hệ thống thực cần logger/giám sát.
            multicaster.setErrorHandler(error ->
                    System.err.println("Listener error: " + error.getMessage()));

            return multicaster;
        }

        @Bean
        OrderListener orderListener() {
            return new OrderListener();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderListener listener = context.getBean(OrderListener.class);
            context.publishEvent(new OrderCreated("ORD-1001"));

            if (!listener.awaitHandled()) {
                throw new IllegalStateException("Listener chua xu ly su kien");
            }

            System.out.println("Đơn hàng: " + listener.getHandledOrderId());
            System.out.println("Dùng event pool: " +
                    listener.getListenerThreadName().startsWith("domain-event-"));
        }
    }
}
```

Chạy trong thư mục dự án:

```bash
gradle run
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows. Hai dòng được **chương trình** in ra trong điều kiện bình thường (ngoài thông tin do Gradle/Spring có thể ghi) là:

```text
Đơn hàng: ORD-1001
Dùng event pool: true
```

**Vì sao hai dòng này có thể kiểm chứng?** Listener ghi `handledOrderId` và `listenerThreadName` trước khi gọi `handled.countDown()`. Luồng `main` chỉ đọc hai giá trị sau `awaitHandled()` trả về `true`. Vì executor đặt `threadNamePrefix = "domain-event-"` và listener hỗ trợ gọi bất đồng bộ, giá trị in ra thể hiện việc listener được thực hiện bởi pool này. Nếu listener không hoàn tất trong 5 giây, chương trình ném exception thay vì in một kết quả thành công sai.

Ví dụ **không** khẳng định thời điểm in ra so với lúc `publishEvent(...)` trả về; lập lịch luồng có thể thay đổi theo từng lần chạy. Ngoài ra, `CountDownLatch(1)` được dùng để kiểm tra **một lần phát sự kiện** trong demo, không đại diện cho cơ chế điều phối vô số event trong production.

### 5.3. Phân tích các điểm quan trọng

1. **Tên bean chính xác:** `@Bean(name = AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)` khiến context sử dụng multicaster được cấu hình.
2. **Bean executor riêng:** `domainEventExecutor()` tạo `ThreadPoolTaskExecutor` với số luồng và hàng đợi có giới hạn; Spring quản lý khởi tạo và hủy bean khi đóng context.
3. **Gắn executor:** `multicaster.setTaskExecutor(domainEventExecutor)` thay cách gọi các listener **cho phép** bất đồng bộ trong context.
4. **Gắn error handler:** `setErrorHandler(...)` nhận lỗi phát sinh trong quá trình gọi listener. Ví dụ chỉ in lỗi; production cần chọn rõ policy ghi log, cảnh báo, retry hoặc chuyển thông điệp vào nơi có bảo đảm lưu trữ khi cần.
5. **Giữ API phát sự kiện:** Code phát vẫn gọi `context.publishEvent(new OrderCreated(...))`. Người phát sự kiện không cần biết đa số listener được multicaster phân phối qua executor nào.

## 6. Tại sao không phải mọi listener đều chuyển sang thread pool?

Từ Spring Framework 6.1, `ApplicationListener` có method `supportsAsyncExecution()`, mặc định trả về `true`. `SimpleApplicationEventMulticaster` chỉ chuyển listener sang executor khi listener cho phép; listener trả về `false` vẫn được gọi trên luồng phát gốc.

Ví dụ quan trọng là `TransactionalApplicationListener`: listener cần đăng ký với giao dịch hiện tại nên không thể tùy ý được chuyển sang luồng khác ở bước dispatch. Các phương thức `@TransactionalEventListener` cần được hiểu theo **pha giao dịch** (ví dụ `AFTER_COMMIT`); không nên xem cấu hình multicaster là cách ép chúng chạy async.

So sánh ba cách cấu hình:

| Cách | Phạm vi | Cần chú ý |
| --- | --- | --- |
| Không set executor trên multicaster | Listener thường chạy đồng bộ | Lỗi listener có thể ảnh hưởng trực tiếp publisher |
| Set executor trên multicaster | Rộng trên các listener cho phép async trong context | Thứ tự hoàn tất, transaction context, thread-local và cách báo lỗi thay đổi |
| `@Async` trên listener được chọn | Chỉ những method được gắn annotation và có cấu hình hỗ trợ `@EnableAsync` | Dễ chọn lọc nhưng exception/return value của async listener có giới hạn riêng |

Không ghép cả `@Async` lẫn executor toàn cục vào một listener chỉ vì muốn "async hơn": điều đó có thể tạo hai tầng điều phối, khó dự đoán thời điểm xử lý và khó quan sát lỗi.

## 7. Xử lý ngoại lệ: synchronous khác asynchronous

### 7.1. Không gắn `ErrorHandler`

Với chế độ đồng bộ mặc định, exception chưa được xử lý từ một listener có thể lan ngược tới nơi gọi `publishEvent(...)` và dừng vòng multicast hiện tại. Vì vậy người phát sự kiện cần hiểu tác dụng của lỗi listener đối với luồng nghiệp vụ.

Khi multicaster đã giao việc cho executor, exception phát sinh trong tác vụ listener thường không được ném trực tiếp về luồng publisher như lỗi đồng bộ. Lỗi có thể được executor/log xử lý; cần giám sát chúng tại nơi thực thi.

### 7.2. Có gắn `ErrorHandler`

`SimpleApplicationEventMulticaster#setErrorHandler(ErrorHandler)` định nghĩa hành vi khi listener ném exception. Nếu handler chỉ log rồi trả về, exception đã được tiêu thụ. Nếu handler ném lại exception, hệ quả phụ thuộc việc listener đang chạy trong luồng publisher hay executor.

Spring còn có các handler tiện ích như `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` và `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER`. Tên của chúng phản ánh chính sách xử lý; đừng chọn `SUPPRESS` nếu nghiệp vụ yêu cầu caller phải nhận lỗi hoặc cần retry.

**Phân biệt hai nguồn lỗi:** `ErrorHandler` xử lý lỗi **bên trong quá trình gọi listener**. Nếu thread pool quá tải và **từ chối nhận task** (ví dụ `TaskRejectedException`), lỗi có thể xảy ra ngay ở bước `execute(...)`/gửi task; không nên giả định handler này sẽ giải quyết mọi trường hợp quá tải.

## 8. Hệ quả khi dùng executor bất đồng bộ toàn cục

### 8.1. Thứ tự thực thi và hoàn thành

Dù có `@Order`, khi các listener được gửi sang pool nhiều luồng thì thứ tự **hoàn thành** không còn được đảm bảo. Listener A được lên lịch trước listener B không có nghĩa A kết thúc trước B. Nếu cần thứ tự nghiệp vụ, nên tổ chức một chuỗi xử lý có kiểm soát hoặc dùng hàng đợi/consumer có chính sách thứ tự rõ ràng.

### 8.2. Transaction, SecurityContext, MDC, ThreadLocal

Task chạy ở thread khác không tự động kế thừa toàn bộ transaction context, `ThreadLocal`, thông tin bảo mật hay MDC của publisher. Nếu listener phụ thuộc các dữ liệu này, cần thiết kế truyền context rõ ràng và kiểm thử thực tế. Với quan sát/trace, Spring có hỗ trợ task decorator như `ContextPropagatingTaskDecorator` khi sử dụng dependency cần thiết; việc "copy context" không khiến transaction của thread gốc tự động được chia sẻ an toàn cho worker.

Nếu một hành động cần chạy **sau commit**, ưu tiên đúng mô hình giao dịch, ví dụ `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`; không dùng task executor toàn cục như cách thay thế cơ chế đồng bộ giao dịch.

### 8.3. Cấu hình giới hạn pool và quá tải

Trong ví dụ:

- `corePoolSize=2` và `maxPoolSize=2` giữ tối đa hai worker của pool cho các tác vụ thường.
- `queueCapacity=20` tạo hàng đợi giới hạn, giúp thấy rõ ngưỡng tài nguyên thay vì để hàng đợi phát triển không kiểm soát.
- Khi cả worker và queue đều đầy, executor có thể từ chối task; phải chọn chính sách phản ứng phù hợp cho nghiệp vụ (ghi nhận thất bại, retry có kiểm soát, hoặc chuyển sang hàng đợi bền vững).
- `setWaitForTasksToCompleteOnShutdown(true)` cùng `setAwaitTerminationSeconds(5)` hỗ trợ đóng ứng dụng có kiểm soát; không đảm bảo mọi task dài hơn 5 giây đều hoàn thành.

Kích thước pool phải dựa trên tải, độ trễ I/O, thời gian xử lý và sức chịu tải hệ thống. Không biến `ApplicationEventMulticaster` trong bộ nhớ thành hàng đợi tin cậy: nó **không tự bảo đảm** persistence, retry, exactly-once hay khôi phục sau crash. Với nghiệp vụ không được phép mất event, cần cân nhắc transactional outbox và message broker.

### 8.4. Các sự kiện vòng đời ứng dụng

Một số listener của Spring và thư viện liên quan cũng lắng nghe sự kiện trong cùng context. Khi đổi multicaster globally, các listener đủ điều kiện async có thể đổi thời điểm hoàn tất so với trước. Không mặc định rằng mọi listener đều an toàn khi chạy ở thread khác; kiểm thử hành vi khởi động, đóng ứng dụng và các listener quan trọng trước khi áp dụng rộng.

## 9. Kiểm tra rằng multicaster tùy biến đang hoạt động

**Kiểm tra tên và loại bean:**

```java
ApplicationEventMulticaster current =
        context.getBean(
                AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME,
                ApplicationEventMulticaster.class);
System.out.println(current.getClass().getSimpleName());
```

Đây là **đoạn kiểm tra chèn vào phần có biến `context`**, không phải chương trình Java độc lập. Cần thêm imports `ApplicationEventMulticaster` và `AbstractApplicationContext` nếu file hiện tại chưa có. Với demo ở trên, dòng do đoạn kiểm tra này in ra sẽ là `SimpleApplicationEventMulticaster`. Điều này chứng minh bean được chọn theo tên, nhưng **chưa** chứng minh executor đang sử dụng; kiểm tra tên luồng với latch như ví dụ mới kiểm tra được phần đó.

**Ma trận kiểm thử cần có:**

| Trường hợp | Kỳ vọng |
| --- | --- |
| Không khai báo bean đặc biệt | Context vẫn phát sự kiện với multicaster mặc định |
| Khai báo bean đúng tên `applicationEventMulticaster` | Context sử dụng multicaster đã cung cấp |
| Listener đủ điều kiện async, executor còn chỗ | Listener có thể chạy trên thread của pool |
| Listener không hỗ trợ async | Vẫn chạy ở luồng phát theo contract |
| Listener ném exception | Hành vi đúng với `ErrorHandler` đã chọn |
| Executor hết khả năng nhận task | Có chiến lược xử lý từ chối phù hợp |
| Dừng context khi còn task | Vòng đời executor đóng theo chính sách cấu hình |
| Listener phụ thuộc transaction/context | Không ngầm giả định context được truyền sang worker |

Nên kiểm tra sự kiện bằng `CountDownLatch`, `CompletableFuture` hoặc công cụ đồng bộ phù hợp. Dùng `Thread.sleep(...)` và kiểm tra kết quả ngay sau một khoảng tùy ý dễ tạo test chập chờn. Một test tốt kiểm tra kết quả nghiệp vụ, tên thread khi cần, error handling và giới hạn thời gian rõ ràng.

## 10. Những lỗi cấu hình phổ biến

1. **Sai tên bean:** Khai báo `@Bean("myMulticaster")` rồi nghĩ Spring tự dùng vì đúng kiểu. Spring cần đúng tên `applicationEventMulticaster` cho hạ tầng.
2. **Khai báo hai bean cùng tên:** Một cấu hình khác đã có bean hạ tầng cùng tên có thể gây xung đột hoặc phụ thuộc chính sách bean overriding của ứng dụng. Cần thống nhất một nguồn cấu hình.
3. **Chỉ khai báo `Executor` bean nhưng không gọi `setTaskExecutor(...)`:** Multicaster không tự lấy executor tùy ý để chuyển mọi listener sang async.
4. **Tự tạo pool mà không quản lý vòng đời:** Dùng `Executors.newFixedThreadPool(...)` trực tiếp rồi bỏ quên `shutdown()` có nguy cơ giữ thread/tài nguyên sau khi context đóng. Ưu tiên executor được Spring quản lý.
5. **Tin rằng lỗi async sẽ đến publisher:** Lỗi bên trong task xảy ra tại thread khác. Theo dõi qua handler, log, metric và chiến lược retry đúng nơi.
6. **Cho rằng `@Order` bảo đảm thứ tự hoàn thành:** Với pool nhiều luồng, lịch chạy và kết thúc không cố định.
7. **Đưa I/O chậm vào mọi listener:** Đổi sang async làm giảm chặn publisher trong điều kiện bình thường, nhưng không loại bỏ giới hạn throughput hay lỗi của hệ thống ngoài.
8. **Bỏ qua listener transactional:** Những listener phụ thuộc pha giao dịch có contract đặc biệt; global executor không thay thế cơ chế `@TransactionalEventListener`.
9. **Tự viết một multicaster đầy đủ khi không cần:** Nếu chỉ muốn executor/error handler, cấu hình `SimpleApplicationEventMulticaster` giúp giữ nguyên cơ chế đăng ký và lọc listener có sẵn.
10. **Thiếu kiểm thử tải và shutdown:** Dễ bỏ sót trường hợp pool cạn tài nguyên, shutdown khi còn task hoặc mất dấu lỗi.

## 11. Quy trình áp dụng an toàn trong dự án thực tế

1. Liệt kê yêu cầu thực tế: thay đổi lỗi listener, tránh giữ publisher, hay cần chiến lược dispatch riêng?
2. Xác nhận phạm vi một `ApplicationContext` và các listener nào có thể bị ảnh hưởng.
3. Đầu tiên tạo bean `applicationEventMulticaster` với `SimpleApplicationEventMulticaster`; chỉ thêm executor khi yêu cầu thật sự cần.
4. Sử dụng executor được quản lý, giới hạn tài nguyên và xác định chính sách quá tải.
5. Quyết định cách log, ném lại, retry và giám sát lỗi listener.
6. Kiểm tra transaction, context propagation, thứ tự, event vòng đời và xử lý khi shutdown.
7. Xác minh qua test có thể lặp lại và đo độ trễ/throughput trên workload đại diện.

**Điểm cần nhớ:** Trong Spring, "thay multicaster mặc định" chủ yếu là **cung cấp bean tên `applicationEventMulticaster`**. Chỉ dùng `setTaskExecutor(...)` khi hiểu tác động của dispatch bất đồng bộ; dùng `setErrorHandler(...)` khi đã xác định chính sách lỗi. Cơ chế Application Events phù hợp để kết nối các bean trong một ứng dụng, nhưng không thay thế một hệ thống message delivery bền vững.

## Tài liệu tham khảo

- [Spring Framework Reference — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): multicaster mặc định và cách khai báo bean tùy biến.
- [Spring Framework 6.2 Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): `setTaskExecutor`, `setErrorHandler` và giới hạn async.
- [Spring Framework Reference — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): ảnh hưởng của async đến thread context và task decorator.
- [Spring Framework 6.2 Javadoc — ApplicationListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationListener.html): `supportsAsyncExecution()`.
