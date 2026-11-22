# Vai trò của ApplicationEventMulticaster trong Spring Framework

## 1. ApplicationEventMulticaster là gì và vì sao cần nó?

Trong Spring Framework, một thành phần có thể thông báo rằng một việc đã xảy ra, chẳng hạn “đơn hàng vừa được tạo”, mà không phải biết những thành phần nào sẽ phản ứng. Thành phần phát thông báo gọi `ApplicationEventPublisher.publishEvent(...)`; các thành phần quan tâm đăng ký làm **listener** (bộ lắng nghe sự kiện).

**`ApplicationEventMulticaster` là giao diện của bộ phận nhận sự kiện từ `ApplicationContext` và phân phối đến những listener phù hợp đã đăng ký trong cùng ngữ cảnh Spring.** Nó là mắt xích điều phối giữa bên phát và bên nhận: quản lý danh sách listener, tìm listener quan tâm đến loại sự kiện, rồi gọi các listener theo chiến lược thực thi được cấu hình.

Đây là cơ chế trao đổi sự kiện **bên trong ứng dụng Spring**. “Multicast” ở đây nghĩa là một sự kiện có thể được chuyển đến nhiều listener phù hợp; nó không có nghĩa là phát gói tin multicast trên mạng.

~~~text
Mã nghiệp vụ
    |
    | ApplicationEventPublisher.publishEvent(event)
    v
ApplicationContext
    |
    | ủy quyền việc phát sự kiện
    v
ApplicationEventMulticaster
    |-- chọn listener phù hợp với loại sự kiện
    |-- áp dụng thứ tự và chính sách thực thi
    +--> Listener A
    +--> Listener B
    +--> Listener C (chỉ khi loại sự kiện khớp)
~~~

Nếu không có tầng điều phối này, bên phát sẽ phải biết và gọi từng bên nhận trực tiếp. Với event multicaster, các listener có thể được thêm hoặc bỏ mà không phải sửa mã phát sự kiện.

## 2. Những trách nhiệm chính

| Trách nhiệm | Ý nghĩa thực tế |
| --- | --- |
| Quản lý đăng ký | Tiếp nhận các `ApplicationListener` dạng đối tượng hoặc bean; cung cấp các thao tác thêm và gỡ listener. |
| Xác định bên nhận | Dựa trên loại sự kiện, kể cả thông tin kiểu tổng quát (generic) khi có thể xác định, để tìm listener phù hợp. |
| Phân phối sự kiện | Gọi một hay nhiều listener khi sự kiện được phát. Một sự kiện không mặc nhiên gửi đến mọi listener bất kể loại. |
| Điều phối cách chạy | Với triển khai hỗ trợ, quyết định listener chạy trực tiếp trong luồng phát hay được giao cho `Executor`. |
| Xử lý lỗi lúc gọi listener | Với triển khai hỗ trợ, áp dụng `ErrorHandler` để xử lý ngoại lệ do listener ném ra. |

Một số phương thức tiêu biểu của giao diện `ApplicationEventMulticaster`:

- `addApplicationListener(listener)` và `addApplicationListenerBean(beanName)`: thêm listener.
- `removeApplicationListener(...)`, `removeApplicationListenerBean(...)`, `removeAllListeners()`: gỡ listener theo phạm vi tương ứng.
- `multicastEvent(ApplicationEvent event)` và `multicastEvent(ApplicationEvent event, ResolvableType eventType)`: phân phối một sự kiện đến các listener quan tâm. Đối số `ResolvableType` giúp giữ thêm thông tin về kiểu tổng quát khi có.

Lưu ý ranh giới trách nhiệm: **`ApplicationEventPublisher` là API nghiệp vụ dùng để phát sự kiện; `ApplicationEventMulticaster` là hạ tầng thực hiện việc phân phối.** Mã nghiệp vụ thông thường chỉ cần gọi `publishEvent(...)`, không cần lấy multicaster ra và gọi trực tiếp.

## 3. Spring sử dụng multicaster như thế nào?

Trong một `ApplicationContext` thông thường, Spring thiết lập một multicaster cho context. Nếu ứng dụng không cung cấp bean có tên chính xác `applicationEventMulticaster`, Spring sử dụng `SimpleApplicationEventMulticaster` mặc định.

Các listener có thể đến từ:

- Bean triển khai `ApplicationListener<E>`; kiểu sự kiện `E` thể hiện nhóm sự kiện muốn nhận.
- Phương thức có `@EventListener` trên bean do Spring quản lý; Spring tạo adapter để đưa phương thức đó vào cơ chế listener.
- Listener được đăng ký theo cơ chế của `ApplicationContext`.

Khi mã gọi `context.publishEvent(event)`, Spring chuẩn bị sự kiện, xác định thông tin kiểu rồi chuyển đến multicaster của context. Với đối tượng thường không kế thừa `ApplicationEvent`, Spring có thể bọc payload vào `PayloadApplicationEvent`; vì thế `@EventListener` vẫn có thể nhận trực tiếp kiểu payload, chẳng hạn `OrderPlaced`.

`AbstractApplicationEventMulticaster` cung cấp phần quản lý và tra cứu listener. `SimpleApplicationEventMulticaster` mở rộng phần đó để thực sự gọi listener. Mỗi listener nhận được sự kiện là kết quả của quá trình ghép loại và các điều kiện riêng của listener; ví dụ `@EventListener(condition = "...")` còn có thể lọc thêm bằng biểu thức.

**Theo mặc định, việc phân phối là đồng bộ trên luồng gọi `publishEvent(...)`.** Nếu một listener xử lý lâu, lời gọi phát sự kiện cũng mất thêm thời gian. Đây là hành vi cần hiểu trước khi xem event như một cách chạy nền.

## 4. Ví dụ Java 17+: một sự kiện, hai listener

Ví dụ dưới đây dùng Spring Framework thuần, không cần Spring Boot. Tạo cấu trúc:

~~~text
application-event-demo/
├── pom.xml
└── src/main/java/ApplicationEventMulticasterDemo.java
~~~

Nội dung `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>application-event-demo</artifactId>
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

Nội dung `src/main/java/ApplicationEventMulticasterDemo.java`:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class ApplicationEventMulticasterDemo {

    public record OrderPlaced(String orderId) {}

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(DemoConfig.class)) {
            System.out.println("Trước khi phát sự kiện");
            context.publishEvent(new OrderPlaced("A-101"));
            System.out.println("Sau khi phát sự kiện");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DemoConfig {
        @Bean
        public StockListener stockListener() {
            return new StockListener();
        }

        @Bean
        public AuditListener auditListener() {
            return new AuditListener();
        }
    }

    public static class StockListener {
        @EventListener
        @Order(10)
        public void handle(OrderPlaced event) {
            System.out.println("Kho: tiếp nhận đơn " + event.orderId());
        }
    }

    public static class AuditListener {
        @EventListener
        @Order(20)
        public void handle(OrderPlaced event) {
            System.out.println("Nhật ký: tiếp nhận đơn " + event.orderId());
        }
    }
}
~~~

Từ thư mục chứa `pom.xml`, dùng Java 17+ và Maven:

~~~powershell
mvn -q compile exec:java -Dexec.mainClass=ApplicationEventMulticasterDemo
~~~

Kết quả tiêu chuẩn trên stdout (không tính thông báo do môi trường Maven tự bổ sung):

~~~text
Trước khi phát sự kiện
Kho: tiếp nhận đơn A-101
Nhật ký: tiếp nhận đơn A-101
Sau khi phát sự kiện
~~~

**Giải thích luồng chạy:**

1. `AnnotationConfigApplicationContext` khởi tạo bean và đăng ký hai phương thức `@EventListener` thông qua hạ tầng listener của Spring.
2. `publishEvent(new OrderPlaced("A-101"))` gửi một đối tượng payload bình thường; Spring xử lý payload đó như một sự kiện.
3. Multicaster tìm cả hai listener nhận `OrderPlaced`. Hai giá trị `@Order` thể hiện thứ tự ưu tiên tương ứng trong lần phân phối đồng bộ.
4. Multicaster mặc định gọi hai phương thức ngay trong luồng phát, nên cả hai dòng xử lý xuất hiện **trước** “Sau khi phát sự kiện”.

Nếu bổ sung listener chỉ nhận `PaymentCaptured`, nó sẽ không được gọi khi phát `OrderPlaced`. Điều này thể hiện nhiệm vụ ghép loại sự kiện với listener, thay vì gọi mọi phương thức có `@EventListener`.

## 5. Cấu hình cách thực thi: đồng bộ và bất đồng bộ

### Mặc định: đồng bộ

`SimpleApplicationEventMulticaster` mặc định chạy listener trong chính luồng gọi `publishEvent(...)`, tương tự dùng `SyncTaskExecutor`.

Ưu điểm: thứ tự dễ quan sát; bên phát biết các listener đồng bộ đã chạy xong khi `publishEvent(...)` trả về; trạng thái gắn với luồng (ví dụ ngữ cảnh giao dịch) có thể còn hiệu lực trong listener.

Giới hạn: một listener chậm sẽ làm bên phát chậm theo. Nếu listener đồng bộ ném ngoại lệ và không có `ErrorHandler`, ngoại lệ thông thường truyền ngược về bên phát và có thể khiến các listener còn lại chưa được gọi.

### Khi muốn dùng bộ thực thi riêng

Có thể khai báo bean tên **`applicationEventMulticaster`** và cấu hình `setTaskExecutor(...)`. Đoạn sau là **phần cấu hình minh họa để đặt trong một lớp `@Configuration` của ứng dụng đang có Spring Context**, không phải chương trình Java độc lập:

~~~java
@Bean
public ThreadPoolTaskExecutor eventTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(50);
    executor.setThreadNamePrefix("app-event-");
    executor.initialize();
    return executor;
}

@Bean(name = "applicationEventMulticaster")
public ApplicationEventMulticaster applicationEventMulticaster(
        ThreadPoolTaskExecutor eventTaskExecutor) {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventTaskExecutor);
    multicaster.setErrorHandler(error ->
            System.err.println("Listener gặp lỗi: " + error.getMessage()));
    return multicaster;
}
~~~

Các kiểu cần import trong cấu hình trên: `org.springframework.context.event.ApplicationEventMulticaster`, `org.springframework.context.event.SimpleApplicationEventMulticaster` và `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor`, cùng `@Bean`. Ví dụ `ErrorHandler` chỉ in lỗi để làm rõ điểm cấu hình; ứng dụng thực tế cần ghi log và giám sát lỗi thích hợp.

Khi dùng `Executor` bất đồng bộ, `publishEvent(...)` thường có thể trở về trước khi listener xử lý xong; thứ tự hoàn tất giữa các listener không còn được bảo đảm. Ngoại lệ trong tác vụ bất đồng bộ cũng không truyền trở lại lời gọi `publishEvent(...)` như trường hợp đồng bộ. Cần chủ động quản lý số luồng, hàng đợi, việc từ chối tác vụ và thời điểm đóng ứng dụng.

**Không phải mọi listener đều được phép chuyển sang luồng khác.** Trong Spring Framework 6.1+, `ApplicationListener.supportsAsyncExecution()` cho biết listener có hỗ trợ thực thi bất đồng bộ hay không; các listener gắn với đồng bộ giao dịch (chẳng hạn `TransactionalApplicationListener`) có thể yêu cầu chạy trong luồng phát ban đầu. Vì thế đặt `TaskExecutor` không có nghĩa là mọi listener đều được chạy nền.

Một lựa chọn khác là đánh dấu **một phương thức** bằng `@Async` bên cạnh `@EventListener` và bật xử lý bất đồng bộ bằng `@EnableAsync`. Cách đó điều khiển từng listener, trong khi thay bean multicaster là thay chính sách phân phối ở phạm vi context. Không nên dùng hai cách mà chưa xác định rõ trách nhiệm.

## 6. Cách xử lý lỗi và thứ tự listener

- **Lỗi đồng bộ:** nếu không cấu hình `ErrorHandler`, ngoại lệ từ listener có thể dừng lượt phân phối và truyền đến mã gọi `publishEvent(...)`. Vì vậy listener nên tự xử lý những lỗi mà nghiệp vụ có thể phục hồi.
- **`setErrorHandler(...)`:** cho phép multicaster xử lý lỗi từng lần gọi listener. Một handler ghi nhận lỗi và không ném tiếp có thể giúp quá trình phân phối tiếp tục, nhưng cũng đồng nghĩa bên phát không tự động biết rằng một listener đã thất bại.
- **Thứ tự:** `@Order` hoặc `Ordered` có thể sắp xếp thứ tự gọi listener phù hợp khi chạy đồng bộ. Không nên xem thứ tự đó là cam kết thứ tự hoàn tất khi có nhiều tác vụ chạy bất đồng bộ.
- **Giao dịch:** listener đồng bộ có thể thực thi trong ngữ cảnh giao dịch của bên phát. Listener chạy trên luồng khác không tự kế thừa ngữ cảnh giao dịch, `ThreadLocal` hay thông tin log của luồng gốc. Nếu nghiệp vụ cần xử lý theo mốc commit/rollback, tìm hiểu `@TransactionalEventListener` và ý nghĩa pha giao dịch, thay vì suy luận rằng phát sự kiện luôn đồng nghĩa “đã commit”.

## 7. Phân biệt những thành phần dễ nhầm

| Thành phần | Vai trò |
| --- | --- |
| `ApplicationEventPublisher` | API để mã nghiệp vụ yêu cầu phát một sự kiện. |
| `ApplicationContext` | Context Spring thường đóng vai trò publisher và ủy quyền cho multicaster. |
| `ApplicationEventMulticaster` | Hợp đồng quản lý listener và phân phối sự kiện. |
| `AbstractApplicationEventMulticaster` | Lớp nền hỗ trợ đăng ký, quản lý và tìm listener phù hợp. |
| `SimpleApplicationEventMulticaster` | Triển khai mặc định thực hiện gọi listener, có thể cấu hình `Executor` và `ErrorHandler`. |
| `ApplicationListener<E>` | Hợp đồng listener theo loại sự kiện. |
| `@EventListener` | Cách khai báo một phương thức bean xử lý sự kiện; Spring đưa phương thức vào cơ chế listener. |

Đừng nhầm event multicaster với hệ thống hàng đợi thông điệp như RabbitMQ/Kafka: Spring Application Events mặc định không lưu sự kiện bền vững, không có xác nhận giao hàng qua mạng và không tự gửi sang tiến trình khác. Nếu ứng dụng tắt đột ngột, sự kiện đang chờ tác vụ bất đồng bộ không có bảo đảm được phát lại.

## 8. Sai lầm thường gặp và cách kiểm tra

1. **Nghĩ `publishEvent(...)` luôn bất đồng bộ.** Thực tế mặc định là đồng bộ; hãy đo thời gian trước/sau lời gọi và quan sát tên luồng của listener.
2. **Đặt `@EventListener` trên đối tượng không do Spring quản lý.** Phương thức như vậy không tự được đăng ký như listener của context; tạo bean hoặc đăng ký listener đúng cách.
3. **Cho rằng một sự kiện sẽ kích hoạt mọi listener.** Kiểm tra kiểu sự kiện, kiểu generic, `condition` và việc listener đã được đăng ký trong context đang phát.
4. **Nghĩ đổi sang `Executor` sẽ giữ nguyên transaction context.** Các thông tin gắn với luồng thường không tự truyền sang luồng khác. Tránh đọc dữ liệu chưa commit theo giả định từ listener chạy nền.
5. **Bỏ qua lỗi listener.** Với đồng bộ, lỗi có thể tác động trực tiếp đến luồng nghiệp vụ; với bất đồng bộ, cần nơi ghi nhận lỗi độc lập.
6. **Dùng sự kiện nội bộ cho yêu cầu giao hàng chắc chắn hoặc liên tiến trình.** Đối với trường hợp cần bền vững, retry và giao nhận giữa các dịch vụ, chọn cơ chế thông điệp/transactional outbox thích hợp.

**Tự kiểm tra:** Trong ví dụ trên, vì sao dòng “Sau khi phát sự kiện” xuất hiện cuối? Nếu cấu hình multicaster dùng thread pool, phần nào của kết quả không còn được bảo đảm? Nếu thêm một listener chỉ nhận `PaymentCaptured`, nó có được gọi khi phát `OrderPlaced` không? Trả lời lần lượt: vì mặc định phân phối đồng bộ; khi dùng thread pool, thời điểm và thứ tự hoàn tất listener có thể thay đổi; listener khác loại không được gọi.

## Tài liệu tham khảo

- [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Javadoc — ApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
- [Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
