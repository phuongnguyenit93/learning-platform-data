# Cấu hình ApplicationEventMulticaster bằng bean trong Spring Framework

## 1. Mục tiêu và bối cảnh

Trong Spring Framework, ứng dụng phát sự kiện qua `ApplicationEventPublisher.publishEvent(...)`; phía nhận dùng `ApplicationListener` hoặc phương thức `@EventListener`. Thành phần làm nhiệm vụ phân phối sự kiện đến những listener phù hợp là **`ApplicationEventMulticaster`**.

Thông thường bạn không cần tự tạo multicaster: `ApplicationContext` tự cung cấp một `SimpleApplicationEventMulticaster`. Tuy nhiên, khi cần kiểm soát cách chạy listener và xử lý lỗi ở cấp phân phối sự kiện, có thể **khai báo một bean với tên chính xác `applicationEventMulticaster`**.

Sau bài này, bạn có thể:

- Giải thích cách `ApplicationContext` chọn multicaster mặc định hay bean do ứng dụng cung cấp.
- Khai báo bean `applicationEventMulticaster` bằng Java Configuration và biết cách dùng với Spring Boot.
- Cấu hình `SimpleApplicationEventMulticaster#setTaskExecutor(...)` cho xử lý đồng bộ hoặc phân phối qua thread pool.
- Cấu hình `setErrorHandler(...)` và hiểu tác động tới việc phát sự kiện khi listener ném exception.
- Chạy một ví dụ Java 17+ có bean multicaster tự khai báo, đo được kết quả, rồi nhận diện các rủi ro với async, transaction và tài nguyên luồng.

## 2. Multicaster nằm ở đâu trong luồng sự kiện?

~~~text
Service / component
      |
      | publishEvent(event)
      v
ApplicationEventPublisher
(thường chính là ApplicationContext)
      |
      v
ApplicationEventMulticaster
      | tìm listener phù hợp với kiểu sự kiện
      | sắp thứ tự gọi listener nếu có Ordered/@Order
      | chọn executor và xử lý lỗi theo cấu hình
      |
      +----> Listener A
      +----> Listener B
      +----> Listener C
~~~

`ApplicationEventPublisher` là API để **phát** sự kiện. `ApplicationEventMulticaster` là chiến lược bên trong context để **phân phối** một sự kiện tới các listener đã được đăng ký. Thông thường mã nghiệp vụ vẫn chỉ phụ thuộc vào `ApplicationEventPublisher`, còn cấu hình bean multicaster được đặt ở tầng cấu hình ứng dụng.

`AbstractApplicationContext` có hằng:

~~~java
AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME
~~~

Giá trị của hằng này là **`"applicationEventMulticaster"`**. Trong lúc khởi tạo context, Spring tìm bean có **đúng tên đó** và yêu cầu nó có kiểu phù hợp với `ApplicationEventMulticaster`. Nếu không có, context tạo một `SimpleApplicationEventMulticaster` mặc định.

Đây là quy ước **theo tên bean**, không chỉ theo kiểu:

- Bean tên `applicationEventMulticaster`, kiểu `SimpleApplicationEventMulticaster` → được dùng để phân phối event cho context.
- Bean kiểu `SimpleApplicationEventMulticaster` nhưng tên `myEventMulticaster` → không tự động thay thế multicaster nội bộ của context chỉ vì trùng kiểu.
- `@Primary` trên một bean khác tên cũng không thay thế quy tắc tìm tên `applicationEventMulticaster`.
- Dùng tên đúng nhưng kiểu không phải `ApplicationEventMulticaster` → context không khởi tạo bình thường.

Với `@Bean` Java Config, cách ít lỗi nhất là dùng trực tiếp hằng được Spring cung cấp:

~~~java
@Bean(name = AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
SimpleApplicationEventMulticaster applicationEventMulticaster() {
    return new SimpleApplicationEventMulticaster();
}
~~~

Đoạn trên là **mảnh cấu hình**, cần đặt trong class `@Configuration` và import đầy đủ; ví dụ chạy độc lập ở mục 5. Chỉ khai báo bean như trên thì hành vi vẫn gần như mặc định; giá trị thực tế thường nằm ở cấu hình **executor** và **error handler**.

## 3. Hai lựa chọn cấu hình chính

### 3.1. `setTaskExecutor(...)`: listener được gọi trên luồng nào?

`SimpleApplicationEventMulticaster` mặc định gọi các listener trên **luồng đang phát sự kiện**, tương đương sử dụng `SyncTaskExecutor`. Với các listener đồng bộ thông thường:

~~~text
publisher thread:
  publishEvent -> listener A (xong)
               -> listener B (xong)
               -> listener C (xong)
               -> trả về cho publisher
~~~

Ưu điểm là dễ theo dõi, dễ kiểm chứng thứ tự và thường giữ được ngữ cảnh của thread gọi. Đổi lại, một listener chạy lâu sẽ giữ cả lời gọi `publishEvent(...)`.

Nếu truyền một executor thực sự chạy bất đồng bộ, ví dụ `ThreadPoolTaskExecutor`, multicaster **lên lịch gọi** những listener cho phép chạy async:

~~~text
publisher thread:
  publishEvent -> submit A -> submit B -> submit C -> trả về

event worker threads:
  A xử lý ...
  B xử lý ...
  C xử lý ...
~~~

Điều này không bảo đảm các listener bắt đầu hoặc kết thúc theo cùng thứ tự. Các listener có thể chạy đồng thời; thời điểm hoàn thành phụ thuộc thread pool, hàng đợi, thời gian thực thi và lỗi.

Từ Spring Framework 6.1, API `ApplicationListener#supportsAsyncExecution()` cho phép một listener nói rằng nó **không hỗ trợ** được multicaster gọi ở thread khác. Các listener đồng bộ hóa theo transaction, chẳng hạn loại `TransactionalApplicationListener`, là ví dụ quan trọng: chúng cần chạy phần đăng ký đồng bộ hóa transaction ở luồng phát sự kiện. Vì vậy, **không được suy ra rằng mọi listener đều bị chuyển sang thread pool chỉ vì đã đặt executor**.

Ngoài ra, `@Async` đặt trên một phương thức `@EventListener` là cơ chế async ở cấp phương thức, khác với việc cấu hình executor trên multicaster. Cần hiểu luồng tác vụ và cách xử lý exception của mỗi cơ chế trước khi dùng chung.

### 3.2. `setErrorHandler(...)`: làm gì khi listener ném exception?

Với listener đồng bộ và **không cấu hình `ErrorHandler`**, exception chưa xử lý thường truyền ngược lên nơi gọi `publishEvent(...)`, làm quá trình phân phối hiện tại dừng lại. Nếu multicaster đã được cấu hình executor async, exception có thể xuất hiện trong thread của executor và không quay lại publisher như trường hợp đồng bộ.

`SimpleApplicationEventMulticaster#setErrorHandler(...)` nhận một `org.springframework.util.ErrorHandler`:

~~~java
multicaster.setErrorHandler(error -> {
    // Ghi nhận / phân loại lỗi rồi quyết định xử lý.
});
~~~

Đây là **mảnh cấu hình**, chưa tạo đầy đủ bean. Spring cũng cung cấp hai chính sách có sẵn trong `org.springframework.scheduling.support.TaskUtils`:

| Chính sách | Ý nghĩa |
| --- | --- |
| Không có `ErrorHandler` | Listener ném exception thì exception không được multicaster nuốt; với đồng bộ có thể truyền về publisher và dừng multicast hiện tại |
| `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` | Ghi log rồi **nuốt** exception; các listener còn lại có cơ hội tiếp tục được gọi |
| `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER` | Ghi log rồi **ném lại** exception; cách truyền lỗi đến publisher vẫn phụ thuộc đồng bộ/async |
| `ErrorHandler` tự viết | Tự quy định cách ghi nhận lỗi và ném lại hay nuốt lỗi; phải có chính sách rõ ràng |

**Cẩn trọng:** “Nuốt exception” có thể khiến publisher tưởng quá trình đã hoàn thành dù một listener thất bại. Chỉ dùng khi listener thật sự độc lập và có cơ chế log/monitoring/retry phù hợp. Error handler của multicaster cũng không tự bắt được mọi lỗi xảy ra **sau đó** trong một tác vụ mà listener đã tự lên lịch qua `@Async`.

## 4. Nên chọn cấu hình nào?

| Nhu cầu | Cấu hình gợi ý | Điều phải kiểm chứng |
| --- | --- | --- |
| Mặc định, không có yêu cầu đặc biệt | Không cần khai báo bean; dùng multicaster mặc định | Listener có chạy lâu và chặn publisher không? |
| Giữ đồng bộ nhưng kiểm soát lỗi | Khai báo `applicationEventMulticaster` và `setErrorHandler(...)` | Lỗi bị truyền tiếp hay nuốt? Các listener sau lỗi có chạy không? |
| Phân phối phần xử lý độc lập qua thread pool | Bean `applicationEventMulticaster` với `ThreadPoolTaskExecutor` được Spring quản lý | Thread pool, queue, shutdown, context thread và thứ tự hoàn thành |
| Listener cần transaction phase | Dùng `@TransactionalEventListener` đúng phase | Không ép chạy async khi phần đăng ký cần transaction của publisher |
| Cần giao nhận bền vững, retry khi app dừng | Thiết kế outbox/message broker chuyên dụng | Multicaster nội bộ không thay thế hàng đợi bền vững |

Với nghiệp vụ có phụ thuộc chặt chẽ “B phải thành công sau A”, một chuỗi xử lý được gọi rõ ràng từ service dễ kiểm soát hơn so với cấu hình multicaster chạy đồng thời và hy vọng thứ tự event đủ bảo đảm.

## 5. Ví dụ Java 17+ hoàn chỉnh: bean multicaster và ErrorHandler

Ví dụ này dùng **Spring Framework thuần**, không cần Spring Boot, cơ sở dữ liệu hay API ngoài. Ta chủ động cấu hình `SyncTaskExecutor` để **kết quả chạy có thứ tự rõ ràng**, đồng thời đặt `ErrorHandler` để mô phỏng một listener thất bại nhưng publisher vẫn tiếp tục phân phối cho listener kế tiếp.

### 5.1. Cấu trúc thư mục và Gradle

~~~text
multicaster-bean-demo/
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── EventMulticasterBeanDemo.java
~~~

Nội dung `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
}

application {
    mainClass = 'demo.EventMulticasterBeanDemo'
}
~~~

`spring-context` kéo theo các thư viện Spring cần thiết qua Gradle. Spring Framework 6.2.x yêu cầu Java 17 trở lên; ví dụ dùng Java 17 hoặc cao hơn. Trong dự án Spring Boot thực tế, thường để dependency management của Boot chọn phiên bản Spring tương thích thay vì tự chốt phiên bản khác.

### 5.2. Mã nguồn `EventMulticasterBeanDemo.java`

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;
import org.springframework.core.annotation.Order;
import org.springframework.core.task.SyncTaskExecutor;

public class EventMulticasterBeanDemo {

    // Spring có thể phát một POJO/record làm event payload.
    public record Registered(String username) {}

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean(name =
                AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
        public SimpleApplicationEventMulticaster applicationEventMulticaster() {
            SimpleApplicationEventMulticaster multicaster =
                    new SimpleApplicationEventMulticaster();

            // Được gọi trên thread phát sự kiện; tương đương hành vi
            // executor mặc định, đặt tường minh để học cách cấu hình.
            multicaster.setTaskExecutor(new SyncTaskExecutor());

            // Ví dụ học tập: in lỗi và không ném lại.
            multicaster.setErrorHandler(error ->
                    System.out.println("handled: "
                            + error.getClass().getSimpleName()
                            + ": " + error.getMessage()));

            return multicaster;
        }

        @Bean
        public Handlers handlers() {
            return new Handlers();
        }
    }

    public static class Handlers {

        @EventListener
        @Order(-10)
        public void first(Registered event) {
            System.out.println("listener -10: " + event.username());
        }

        @EventListener
        @Order(0)
        public void fail(Registered event) {
            throw new IllegalStateException("demo failure");
        }

        @EventListener
        @Order(10)
        public void last(Registered event) {
            System.out.println("listener 10: " + event.username());
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            Object registeredMulticaster = context.getBean(
                    AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME);

            System.out.println("multicaster bean = "
                    + registeredMulticaster.getClass().getSimpleName());

            System.out.println("publisher: before");
            context.publishEvent(new Registered("Mai"));
            System.out.println("publisher: after");
        }
    }
}
~~~

Các điểm cần nhìn trong code:

1. `AppConfig` là cấu hình được `AnnotationConfigApplicationContext` nạp khi khởi tạo.
2. Phương thức `@Bean` được gắn **tên chính xác** bằng hằng `APPLICATION_EVENT_MULTICASTER_BEAN_NAME`, nên context dùng nó làm multicaster nội bộ.
3. `Registered` là Java record. Spring có thể phát đối tượng bất kỳ làm event payload; không bắt buộc kế thừa `ApplicationEvent`.
4. `Handlers` là bean chứa ba phương thức `@EventListener` có order khác nhau.
5. Handler giữa ném `IllegalStateException`. `ErrorHandler` do ta cấu hình xử lý lỗi và **không ném lại**, nên listener cuối vẫn được gọi.

### 5.3. Chạy và kết quả

Từ thư mục `multicaster-bean-demo`, với JDK 17+ và Gradle đã cài:

~~~bash
gradle run
~~~

Nếu có Gradle Wrapper, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows thay cho `gradle run`.

Các dòng do ứng dụng tự in ra **theo thứ tự**:

~~~text
multicaster bean = SimpleApplicationEventMulticaster
publisher: before
listener -10: Mai
handled: IllegalStateException: demo failure
listener 10: Mai
publisher: after
~~~

Gradle có thể có thêm log build; bảng trên chỉ biểu diễn các dòng `System.out.println` của ví dụ.

Vì listener chạy đồng bộ, `publishEvent` chỉ trả về sau listener cuối. Nếu bỏ lệnh `multicaster.setErrorHandler(...)` mà giữ listener `fail`, lỗi sẽ truyền ra lời gọi `publishEvent`; dòng `listener 10: Mai` và `publisher: after` không còn được thực thi theo đường đi thông thường. Đây là cách kiểm tra rõ giá trị của việc cấu hình bean multicaster đối với lỗi.

**Ranh giới của ví dụ:** chính sách in lỗi và nuốt lỗi chỉ nhằm minh họa đường đi điều khiển. Khi triển khai thật, hãy ghi log có ngữ cảnh và xác định trường hợp nào được phép tiếp tục, trường hợp nào phải báo lỗi lên người gọi.

## 6. Cấu hình async bằng bean và ThreadPoolTaskExecutor

Khi listener xử lý tác vụ độc lập, ví dụ gửi thông báo hoặc tính toán phụ không cần chặn publisher, có thể chọn một thread pool riêng cho event. Để tránh tạo thread vô hạn, cấu hình kích thước core, max và hàng đợi phù hợp với tải thực tế.

**Đây là cấu hình thay thế cho `AppConfig` đồng bộ ở mục 5**, không được cùng khai báo hai bean tên `applicationEventMulticaster` trong một context. Đặt đoạn sau vào một class cấu hình của ứng dụng Spring đã có các listener:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.support.TaskUtils;

@Configuration(proxyBeanMethods = false)
public class AsyncEventConfiguration {

    @Bean("eventTaskExecutor")
    public ThreadPoolTaskExecutor eventTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("app-event-");
        return executor;
    }

    @Bean(name =
            AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
    public SimpleApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventTaskExecutor")
            ThreadPoolTaskExecutor executor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();

        multicaster.setTaskExecutor(executor);

        // Ví dụ chính sách: log lỗi rồi ném tiếp ở thread thực thi.
        multicaster.setErrorHandler(
                TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER);

        return multicaster;
    }
}
~~~

Đoạn này là **cấu hình tích hợp vào ứng dụng hiện có** (không phải một chương trình Java độc lập). Khi đưa vào dự án, class cần nằm trong phạm vi component scan hoặc được import bằng `@Import(AsyncEventConfiguration.class)`. Nó sử dụng các API trong `spring-context` và `spring-context-support`? **Không cần spring-context-support** ở đây; `ThreadPoolTaskExecutor` và `TaskUtils` đều thuộc `spring-context`. Việc đặt executor làm bean để Spring quản lý giúp framework khởi tạo và xử lý vòng đời của thread pool; không tạo pool mới bằng `new ThreadPoolTaskExecutor()` ngay trong mỗi lần phát event.

Các con số `2 / 4 / 100` là ví dụ, **không phải thông số mặc định phù hợp cho mọi hệ thống**. Hãy điều chỉnh theo độ dài task, mức tải, khả năng chịu hàng đợi và chính sách khi quá tải.

**Tác động quan trọng của cấu hình async:**

- `publishEvent(...)` có thể kết thúc trước khi các listener async xong việc. Vì vậy, không viết code kiểu “`publishEvent` xong nghĩa là email đã gửi”.
- `@Order` vẫn có thể quyết định thứ tự **điều phối/submission**, nhưng không bảo đảm các task hoàn tất đúng thứ tự.
- Exception xảy ra trong worker thread thường **không quay lại thread publisher**. `LOG_AND_PROPAGATE_ERROR_HANDLER` log rồi ném lại trong ngữ cảnh gọi listener; không biến lỗi async thành exception đồng bộ cho publisher.
- Khi quá tải, executor có thể từ chối nhận tác vụ hoặc áp dụng chính sách từ chối riêng. Theo dõi rejected tasks, queue, active threads và chính sách shutdown; không giả định mọi event được xử lý thành công.
- `ThreadLocal`, logging MDC, security context và transaction context ở publisher không tự nhiên đi theo một tác vụ sang thread khác. Với dữ liệu cần thiết, truyền qua event payload bất biến hoặc dùng cơ chế context propagation được cấu hình rõ ràng; **không dựa vào transaction hiện tại tồn tại trên worker thread**.
- Một số listener không hỗ trợ async ở mức multicaster vẫn chạy trên thread phát sự kiện; đây là hành vi nhằm bảo toàn ngữ nghĩa của những listener đó.

Nếu phải chờ thật sự để kiểm tra task async, trong test nên dùng `CountDownLatch` hoặc cơ chế chờ có timeout rõ ràng. Không đánh giá thành công dựa trên `Thread.sleep(100)` vì scheduler và máy CI có thể khác nhau.

## 7. Cấu hình trong ứng dụng Spring Boot

Trong Spring Boot, cách khai báo bean vẫn giống Spring Framework: đưa cấu hình `@Configuration` vào vùng Boot quét bean (hoặc import) và dùng đúng tên `applicationEventMulticaster`. Không cần tự gọi `context.addApplicationListener(...)` cho những phương thức `@EventListener` được phát hiện bình thường.

Ví dụ dạng ngắn dành cho Boot:

~~~java
@Configuration(proxyBeanMethods = false)
public class EventsConfig {

    @Bean(name = "applicationEventMulticaster")
    public SimpleApplicationEventMulticaster applicationEventMulticaster() {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setErrorHandler(
                TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER);
        return multicaster;
    }
}
~~~

Đây là đoạn **tích hợp vào ứng dụng Boot**, cần các import Spring tương ứng. Với Boot, nên để starter/BOM quản lý phiên bản Spring, tránh khai báo tay phiên bản `spring-context` không khớp. Có thể giữ đồng bộ và chỉ tùy chỉnh `ErrorHandler`; cấu hình thread pool là một lựa chọn riêng, không bắt buộc.

Những trường hợp thường gây nhầm:

- Chỉ khai báo `@Bean("myMulticaster")` rồi nghĩ Boot đã thay đổi dispatcher nội bộ: tên này không phải tên mà context tìm.
- Tạo `SimpleApplicationEventMulticaster` bằng `new` ở service và tự gọi nó: đối tượng đó không tự biết danh sách listener do container quản lý.
- Thêm `@EnableAsync` chỉ để muốn multicaster dùng executor: `@EnableAsync` kích hoạt cơ chế `@Async`, không tự thay `applicationEventMulticaster` bằng một multicaster bất đồng bộ.
- Cấu hình cả multicaster async lẫn `@Async` trên listener mà không phân tích việc lên lịch ở hai lớp.
- Định nghĩa hai bean trùng tên `applicationEventMulticaster` trong các cấu hình khác nhau: tùy thiết lập context, ứng dụng có thể báo lỗi trùng định nghĩa hoặc ghi đè một cấu hình ngoài ý muốn.

## 8. Nếu dự án dùng XML bean configuration

Quy tắc **tên bean** cũng áp dụng khi cấu hình bằng XML. Đoạn dưới là **một phần cấu hình** của file Spring XML có khai báo namespace `beans`, với `eventTaskExecutor` đã được định nghĩa ở nơi khác:

~~~xml
<bean id="applicationEventMulticaster"
      class="org.springframework.context.event.SimpleApplicationEventMulticaster">
    <property name="taskExecutor" ref="eventTaskExecutor"/>
</bean>
~~~

Nếu muốn giữ đồng bộ, bỏ phần `taskExecutor` hoặc khai báo `SyncTaskExecutor` phù hợp. Với dự án mới dùng Java Configuration/Spring Boot, `@Bean` thường dễ theo dõi và kiểm tra bằng Java hơn. Không khai báo XML và Java cùng định nghĩa multicaster khác nhau trong một context mà chưa xác định chiến lược cấu hình thống nhất.

## 9. Tương tác với @Order, @Async và transaction

### 9.1. Thứ tự listener

Nếu listener có `@Order` hoặc implement `Ordered`, Spring dùng giá trị order khi chuẩn bị danh sách listener phù hợp. **Số nhỏ có ưu tiên cao hơn**: `-10` trước `0` trước `10`. Nhưng nếu dùng executor bất đồng bộ, việc xếp danh sách chỉ tác động thứ tự gọi `executor.execute(...)`; **thứ tự hoàn tất** không được bảo đảm. Các listener có cùng mức order không nên được thiết kế với quan hệ phụ thuộc ngầm.

### 9.2. `@Async` ở cấp phương thức

`@Async` trên `@EventListener` cần hỗ trợ async của Spring (`@EnableAsync` hoặc cấu hình tương đương). Khi listener tự chạy theo `@Async`, lỗi phát sinh bên trong nhiệm vụ được ủy quyền có cơ chế thông báo/giám sát riêng; `ErrorHandler` của multicaster không thay thế handler cho lỗi của các nhiệm vụ `@Async` đã trả quyền điều khiển.

Không phải ứng dụng nào cũng cần đặt async trên cả hai cấp. Thường chọn một chiến lược có chủ đích: async chỉ trên những listener riêng lẻ, hoặc executor dành cho nhiều listener đủ điều kiện.

### 9.3. `@TransactionalEventListener`

`@TransactionalEventListener` liên kết xử lý sự kiện với transaction phase, mặc định là `AFTER_COMMIT`. Nó không chỉ là `@EventListener` có `@Order` đặc biệt.

- Listener transaction cần đăng ký đồng bộ hóa vào transaction gốc ở thread phù hợp; vì thế loại listener này được đánh dấu không hỗ trợ multicaster tự chuyển sang executor async ở bước đăng ký.
- Nếu publish khi **không có transaction** đang hoạt động, `@TransactionalEventListener` theo mặc định không được kích hoạt, trừ khi bật `fallbackExecution = true`.
- Nội dung xử lý sau commit chịu quy tắc truy cập tài nguyên/transaction của giai đoạn đó; đừng giả định một task chạy ở thread pool vẫn đang có transaction của publisher.
- Muốn gửi message ra ngoài **chỉ sau commit thành công**, dùng phase đúng, và nếu cần giao nhận chắc chắn qua sự cố ứng dụng thì thiết kế outbox.

Ví dụ annotation minh họa:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(Registered event) {
    // Chỉ thực hiện sau commit trong một transaction hợp lệ.
}
~~~

Đây là đoạn minh họa cần thêm `spring-tx`, import `TransactionPhase` và `TransactionalEventListener`, cấu hình transaction manager và lớp `Registered` tương ứng; nó không thuộc ví dụ chạy độc lập ở mục 5.

## 10. Lỗi cấu hình thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra hoặc sửa |
| --- | --- | --- |
| Đã khai báo multicaster nhưng listener vẫn chạy đồng bộ | Bean không đúng tên; hoặc chưa cấu hình executor async; hoặc listener không hỗ trợ async | Xác nhận có đúng bean tên `applicationEventMulticaster`; kiểm tra executor và loại listener |
| `@EventListener` không được gọi | Listener không phải bean, loại payload không khớp, cấu hình không được scan/import | Kiểm tra bean registration, method signature, event payload |
| Không thấy exception ở `publishEvent` | `ErrorHandler` đang suppress; hoặc listener chạy async | Kiểm tra policy, log của executor, cơ chế thông báo lỗi |
| Một listener hỏng làm các listener phía sau không chạy | Xử lý đồng bộ và exception được truyền tiếp | Bắt lỗi tại listener nơi hợp lý hoặc cấu hình ErrorHandler có chủ đích |
| Có `@Order` nhưng log hoàn thành lộn xộn | Executor chạy song song | Đừng dùng order làm bảo đảm hoàn thành; ghi nhận task và phụ thuộc rõ ràng |
| Listener async không truy cập được transaction hay MDC như trước | Ngữ cảnh thread không tự lan truyền | Truyền dữ liệu cần thiết qua payload và thiết lập context propagation phù hợp |
| Ứng dụng khó tắt do task event còn chạy | Executor lifecycle/shutdown không được quản lý tốt | Dùng executor bean do Spring quản lý, cấu hình và kiểm tra shutdown |
| Thread pool tắc nghẽn, xử lý event chậm | Pool/queue nhỏ hoặc listener giữ thread quá lâu | Đo độ dài task, queue, active thread và điều chỉnh tải/chính sách từ chối |
| Spring lỗi lúc khởi tạo | Tên bean trùng, kiểu bean sai hoặc dependency cycle | Kiểm tra tên `applicationEventMulticaster`, kiểu `ApplicationEventMulticaster` và dependency |

**Đừng tự thêm listener trực tiếp vào một multicaster tự tạo chỉ để “kết nối” với `@EventListener`**. Khi bean được Spring chọn làm multicaster nội bộ, framework sẽ quản lý việc phát hiện và đăng ký listener thích hợp. Nếu muốn thay đổi quy tắc lọc hoặc lập lịch ở mức rất sâu, phải hiểu hợp đồng `ApplicationEventMulticaster` và cách context khởi tạo nó trước khi viết một implementation hoàn toàn mới.

## 11. Kiểm chứng cấu hình đúng cách

Sau khi thêm bean, một bộ kiểm tra nhỏ có giá trị hơn chỉ nhìn cấu hình:

1. **Đúng bean**: tra cứu `context.getBean(AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)`; xác nhận kiểu/configuration đúng mong muốn.
2. **Đồng bộ**: in tên thread và thời điểm trước/sau `publishEvent`; listener đồng bộ phải xử lý trong lời gọi.
3. **ErrorHandler**: tạo listener cố ý ném lỗi trong test, kiểm tra các listener sau đó có được gọi hay không và lỗi có truyền tới publisher hay không.
4. **Executor async**: dùng `CountDownLatch` hoặc `CompletableFuture` chờ với timeout để chắc chắn task đã hoàn tất, không đọc kết quả ngay sau `publishEvent` rồi kết luận.
5. **Thứ tự**: kiểm chứng thứ tự điều phối nếu cần; với async kiểm tra tính đúng đắn dù thời điểm hoàn tất thay đổi.
6. **Transaction**: có bài test transaction thật cho phase `BEFORE_COMMIT`/`AFTER_COMMIT` khi tính năng có sử dụng transaction.
7. **Vận hành**: đo mức tải, độ dài queue, số thread đang chạy, lỗi từ listener và hành vi shutdown.

Trong môi trường production, cần cân nhắc giữa việc trả kết quả nhanh cho request và tính chắc chắn của công việc phía sau. Application event là cơ chế giao tiếp **nội bộ application context**; cấu hình thread pool không biến event thành message bền vững qua restart hay thay thế một hệ thống hàng đợi.

## 12. Câu hỏi tự kiểm tra

**1.** Khai báo `@Bean("customMulticaster")` kiểu `SimpleApplicationEventMulticaster` có tự thay thế multicaster nội bộ không?

**Đáp án:** Không. `AbstractApplicationContext` tìm bean theo tên `applicationEventMulticaster`.

**2.** Bean multicaster có executor `ThreadPoolTaskExecutor`. Có thể kết luận mọi listener đều chạy trên worker thread không?

**Đáp án:** Không. Listener khai báo không hỗ trợ async, đặc biệt listener transaction-synchronized, cần chạy trên thread publisher ở phần xử lý phù hợp.

**3.** Listener A thất bại nhưng `ErrorHandler` chỉ log rồi không ném lại. Listener B có được gọi không?

**Đáp án:** Trong ví dụ đồng bộ với `SimpleApplicationEventMulticaster`, có. Tuy nhiên, A đã thất bại; cần có chính sách xử lý hậu quả rõ ràng thay vì hiểu đây là thành công toàn bộ.

**4.** Gắn `@Order(-10)` cho A và `@Order(10)` cho B, đồng thời chạy multicaster trên thread pool. B có chắc hoàn tất sau A không?

**Đáp án:** Không. Order không bảo đảm thời điểm hoàn tất của tác vụ async.

**5.** Muốn chạy listener sau commit và vẫn giữ đúng transaction semantics cần chú ý gì?

**Đáp án:** Dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` và không giả định thread pool của multicaster tự mang transaction context sang thread khác. Nếu đòi hỏi giao nhận bền vững, thiết kế outbox/message broker riêng.

## 13. Tài liệu tham khảo

- Spring Framework Reference — Standard and Custom Events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Javadoc `AbstractApplicationContext` (hằng tên bean và cơ chế khởi tạo): https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Javadoc `SimpleApplicationEventMulticaster` (executor và error handler): https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Javadoc `ApplicationListener` (hỗ trợ chạy async): https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationListener.html
- Javadoc `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Reference — Observability and event context propagation: https://docs.spring.io/spring-framework/reference/integration/observability.html
